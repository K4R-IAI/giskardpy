from giskardpy.plugin import PluginBehavior
from giskardpy import logging
from sortedcontainers import SortedList

class TreeManager():

    class ManagerNode():
        def __init__(self, node, parent, position):
            self.node = node
            self.parent = parent
            self.position = position
            self.disabled_children = SortedList()
            self.enabled_children = SortedList()

        def __lt__(self, other):
            return self.position < other.position

        def __gt__(self, other):
            return self.position > other.position

        def __eq__(self, other):
            return self.node == other.node and self.parent == other.parent

        def disable_child(self, manager_node):
            self.enabled_children.remove(manager_node)
            self.disabled_children.add(manager_node)
            if isinstance(self.node, PluginBehavior):
                self.node.remove_plugin(manager_node.node.name)
            else:
                self.node.remove_child(manager_node.node)

        def enable_child(self, manager_node):
            self.disabled_children.remove(manager_node)
            self.enabled_children.add(manager_node)
            if isinstance(self.node, PluginBehavior):
                self.node.add_plugin(manager_node.node)
            else:
                idx = self.enabled_children.index(manager_node)
                self.node.insert_child(manager_node.node, idx)

        def add_child(self, manager_node):
            if isinstance(self.node, PluginBehavior):
                self.enabled_children.add(manager_node)
                self.node.add_plugin(manager_node.node)
            else:
                if manager_node.position < 0:
                    manager_node.position = 0
                    if self.enabled_children:
                        manager_node.position = max(manager_node.position, self.enabled_children[-1].position + 1)
                    if self.disabled_children:
                        manager_node.position = max(manager_node.position, self.disabled_children[-1].position + 1)
                    idx = manager_node.position
                else:
                    idx = self.disabled_children.bisect_left(manager_node)
                    for c in list(self.disabled_children.islice(start=idx)):
                        c.position += 1
                    idx = self.enabled_children.bisect_left(manager_node)
                    for c in list(self.enabled_children.islice(start=idx)):
                        c.position += 1
                self.node.insert_child(manager_node.node, idx)
                self.enabled_children.add(manager_node)

        def remove_child(self, manager_node):
            if isinstance(self.node, PluginBehavior):
                if manager_node in self.enabled_children:
                    self.enabled_children.remove(manager_node)
                    self.node.remove_plugin(manager_node.node.name)
                elif manager_node in self.disabled_children:
                    self.disabled_children.remove(manager_node)
                else:
                    raise RuntimeError('could not remove node from parent. this probably means that the tree is inconsistent')
            else:
                if manager_node in self.enabled_children:
                    self.enabled_children.remove(manager_node)
                    self.node.remove_child(manager_node.node)
                elif(manager_node in self.disabled_children):
                    self.disabled_children.remove(manager_node)
                else:
                    raise RuntimeError('could not remove node. this probably means that the tree is inconsistent')
                idx = self.disabled_children.bisect_right(manager_node)
                for c in list(self.disabled_children.islice(start=idx)):
                    c.position -= 1
                idx = self.enabled_children.bisect_right(manager_node)
                for c in list(self.enabled_children.islice(start=idx)):
                    c.position -= 1

    def __init__(self, tree):
        self.tree = tree
        self.tree_nodes = {}
        self.init_map(tree.root, None, 0)

    def init_map(self, node, parent, idx):
        manager_node = TreeManager.ManagerNode(node=node, parent=parent, position=idx)
        if parent != None:
            parent.enabled_children.add(manager_node)
        if isinstance(node, PluginBehavior):
            children = node.get_plugins()
            for child_name in children.keys():
                child_node = TreeManager.ManagerNode(node=children[child_name], parent=manager_node, position=0)
                self.tree_nodes[child_name] = child_node
                manager_node.enabled_children.add(child_node)
        self.tree_nodes[node.name] = manager_node
        for idx, child in enumerate(node.children):
            self.init_map(child, manager_node, idx)


    def disable_node(self, node_name):
        t = self.tree_nodes[node_name]
        if t.parent != None:
            return t.parent.disable_child(t)
        else:
            logging.logwarn('cannot disable root node')
            return False


    def enable_node(self, node_name):
        t = self.tree_nodes[node_name]
        if t.parent != None:
            t.parent.enable_child(t)
        else:
            logging.loginfo('root node')


    def insert_node(self, node, parent_name, position=-1):
        if node.name in self.tree_nodes.keys():
            raise ValueError('node with that name already exists')
        parent = self.tree_nodes[parent_name]
        tree_node = TreeManager.ManagerNode(node=node, parent=parent, position=position)
        parent.add_child(tree_node)
        self.tree_nodes[node.name] = tree_node

    def remove_node(self, node_name):
        node = self.tree_nodes[node_name]
        parent = node.parent
        del self.tree_nodes[node_name]
        parent.remove_child(node)

    def get_node(self, node_name):
        return self.tree_nodes[node_name].node

