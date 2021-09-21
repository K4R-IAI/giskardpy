from collections import OrderedDict, defaultdict, deque
from copy import deepcopy

import numpy as np
import rospy
from sensor_msgs.msg import JointState
from sortedcontainers import SortedKeyList
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from giskardpy import RobotName
from giskardpy.utils.tfwrapper import kdl_to_np, np_vector, np_point


class KeyDefaultDict(defaultdict):
    """
    A default dict where the key is passed as parameter to the factory function.
    """

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)
            return ret


class FIFOSet(set):
    def __init__(self, data, max_length=None):
        if len(data) > max_length:
            raise ValueError('len(data) > max_length')
        super(FIFOSet, self).__init__(data)
        self.max_length = max_length
        self._data_queue = deque(data)

    def add(self, item):
        if len(self._data_queue) == self.max_length:
            to_delete = self._data_queue.popleft()
            super(FIFOSet, self).remove(to_delete)
            self._data_queue.append(item)
        super(FIFOSet, self).add(item)

    def remove(self, item):
        self.remove(item)
        self._data_queue.remove(item)


class JointStates(defaultdict):
    class _JointState(object):
        derivative_to_name = {
            0: 'position',
            1: 'velocity',
            2: 'acceleration',
            3: 'jerk',
            4: 'snap',
            5: 'crackle',
            6: 'pop',
        }

        def __init__(self, position=0, velocity=0, acceleration=0, jerk=0, snap=0, crackle=0, pop=0):
            self.position = position
            self.velocity = velocity
            self.acceleration = acceleration
            self.jerk = jerk
            self.snap = snap
            self.crackle = crackle
            self.pop = pop

        def set_derivative(self, d, item):
            setattr(self, self.derivative_to_name[d], item)

        def __str__(self):
            return '{}'.format(self.position)

        def __repr__(self):
            return str(self)

    def __init__(self):
        super(JointStates, self).__init__(self._JointState)

    @classmethod
    def from_msg(cls, msg, prefix=None):
        """
        :type msg: JointState
        :rtype: JointStates
        """
        self = cls()
        for i, joint_name in enumerate(msg.name):
            joint_name = PrefixName(joint_name, prefix)
            sjs = cls._JointState(position=msg.position[i],
                                  velocity=msg.velocity[i] if msg.velocity else 0,
                                  acceleration=0,
                                  jerk=0,
                                  snap=0,
                                  crackle=0,
                                  pop=0)
            self[joint_name] = sjs
        return self

    def __deepcopy__(self, memodict={}):
        new_js = JointStates()
        for joint_name, joint_state in self.items():
            new_js[joint_name] = deepcopy(joint_state)
        return new_js


class Trajectory(object):
    def __init__(self):
        self.clear()

    def clear(self):
        self._points = OrderedDict()

    def get_exact(self, time):
        return self._points[time]

    def set(self, time, point):
        if len(self._points) > 0 and list(self._points.keys())[-1] > time:
            raise KeyError(u'Cannot append a trajectory point that is before the current end time of the trajectory.')
        self._points[time] = point

    def delete(self, time):
        del self._points[time]

    def delete_last(self):
        self.delete(self._points.keys()[-1])

    def items(self):
        return self._points.items()

    def keys(self):
        return self._points.keys()

    def values(self):
        return self._points.values()

    def to_msg(self, sample_period, controlled_joints, fill_velocity_values):
        """
        :type traj: giskardpy.data_types.Trajectory
        :return: JointTrajectory
        """
        trajectory_msg = JointTrajectory()
        trajectory_msg.header.stamp = rospy.get_rostime() + rospy.Duration(0.5)
        trajectory_msg.joint_names = controlled_joints
        for time, traj_point in self.items():
            p = JointTrajectoryPoint()
            p.time_from_start = rospy.Duration(time * sample_period)
            for joint_name in controlled_joints:
                if joint_name in traj_point:
                    p.positions.append(traj_point[joint_name].position)
                    if fill_velocity_values:
                        p.velocities.append(traj_point[joint_name].velocity)
                else:
                    raise NotImplementedError(u'generated traj does not contain all joints')
            trajectory_msg.points.append(p)
        return trajectory_msg


class Collision(object):
    def __init__(self, link_a, body_b, link_b, position_on_a, position_on_b, contact_normal, contact_distance):
        self.map_P_a = list(position_on_a)
        self.map_P_a.append(1)
        self.map_P_b = list(position_on_b)
        self.map_P_b.append(1)
        self.map_V_n = list(contact_normal)
        self.map_V_n.append(0)
        self.contact_distance = contact_distance
        self.original_link_a = link_a
        self.link_a = link_a
        self.body_b = body_b
        self.original_link_b = link_b
        self.link_b = link_b
        self.old_key = (link_a, body_b, link_a)
        self.new_a_P_a = None
        self.root_P_b = None
        self.new_b_P_b = None
        self.new_b_V_n = None
        self.root_V_n = None

    def get_link_b_hash(self):
        return self.link_b.__hash__()

    def get_body_b_hash(self):
        return self.body_b.__hash__()

    def reverse(self):
        return Collision(link_a=self.original_link_b,
                         body_b=self.body_b,
                         link_b=self.original_link_a,
                         position_on_a=self.map_P_b,
                         position_on_b=self.map_P_a,
                         contact_normal=-self.map_V_n,
                         contact_distance=self.contact_distance)


class CollisionMatrix(dict):
    pass


class Collisions(object):

    def __init__(self, world, collision_list_size):
        """
        :type robot: giskardpy.model.world.WorldTree
        """
        self.world = world
        self.robot = self.world.groups[RobotName]
        self.robot_root = self.robot.root_link_name
        self.root_T_map = self.robot.compute_fk_np(self.robot_root, self.world.root_link_name)
        self.collision_list_size = collision_list_size

        # @profile
        def sort(x):
            return x.contact_distance

        # @profile
        def default_f():
            return SortedKeyList([self._default_collision('', '', '')] * collision_list_size,
                                 key=sort)

        self.default_result = default_f()

        self.self_collisions = defaultdict(default_f)
        self.external_collision = defaultdict(default_f)
        self.external_collision_long_key = defaultdict(lambda: self._default_collision('', '', ''))
        self.all_collisions = set()
        self.number_of_self_collisions = defaultdict(int)
        self.number_of_external_collisions = defaultdict(int)

    @profile
    def add(self, collision):
        """
        :type collision: Collision
        :return:
        """
        collision = self.transform_closest_point(collision)
        self.all_collisions.add(collision)

        # if collision.get_body_b() == self.robot.name:
        #     key = collision.get_link_a(), collision.get_link_b()
        #     self.self_collisions[key].add(collision)
        #     self.number_of_self_collisions[key] = min(self.collision_list_size,
        #                                               self.number_of_self_collisions[key] + 1)
        # else:
        key = collision.link_a
        self.external_collision[key].add(collision)
        self.number_of_external_collisions[key] = min(self.collision_list_size,
                                                      self.number_of_external_collisions[key] + 1)
        key_long = (collision.original_link_a, collision.body_b, collision.original_link_b)
        if key_long not in self.external_collision_long_key:
            self.external_collision_long_key[key_long] = collision
        else:
            self.external_collision_long_key[key_long] = min(collision, self.external_collision_long_key[key_long],
                                                             key=lambda x: x.contact_distance)

    def transform_closest_point(self, collision):
        """
        :type collision: Collision
        :rtype: Collision
        """
        # if collision.get_body_b() == self.robot.name:
        #     return self.transform_self_collision(collision)
        # else:
        return self.transform_external_collision(collision)

    def transform_self_collision(self, collision):
        """
        :type collision: Collision
        :rtype: Collision
        """
        link_a = collision.original_link_a
        link_b = collision.original_link_b
        new_link_a, new_link_b = self.robot.get_chain_reduced_to_controlled_joints(link_a, link_b)
        if new_link_a > new_link_b:
            collision = collision.reverse()
            new_link_a, new_link_b = new_link_b, new_link_a

        new_b_T_r = self.robot.compute_fk_np(new_link_b, self.robot_root)
        new_a_T_r = self.robot.compute_fk_np(new_link_a, self.robot_root)
        collision.link_a = new_link_a
        collision.link_b = new_link_b

        new_b_T_map = np.dot(new_b_T_r, self.root_T_map)

        new_a_P_pa = np.dot(np.dot(new_a_T_r, self.root_T_map), collision.map_P_a)
        new_b_P_pb = np.dot(new_b_T_map, collision.map_P_b)
        # r_P_pb = np.dot(self.root_T_map, np_point(*closest_point.position_on_b))
        new_b_V_n = np.dot(new_b_T_map, collision.map_V_n)
        collision.new_a_P_a = new_a_P_pa
        collision.new_b_P_b = new_b_P_pb
        collision.new_b_V_n = new_b_V_n
        return collision

    @profile
    def transform_external_collision(self, collision):
        """
        :type collision: Collision
        :rtype: Collision
        """
        movable_joint = self.robot.get_controlled_parent_joint(collision.original_link_a)
        new_a = self.robot.joints[movable_joint].child_link_name
        new_a_T_r = self.robot.compute_fk_np(new_a, self.robot_root)
        collision.link_a = new_a

        new_a_P_pa = np.dot(np.dot(new_a_T_r, self.root_T_map), collision.map_P_a)
        r_P_pb = np.dot(self.root_T_map, collision.map_P_b)
        r_V_n = np.dot(self.root_T_map, collision.map_V_n)
        collision.new_a_P_a = new_a_P_pa
        collision.root_P_b = r_P_pb
        collision.root_V_n = r_V_n
        return collision

    def _default_collision(self, link_a, body_b, link_b):
        c = Collision(link_a, body_b, link_b, [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 1, 0], 100)
        c.new_a_P_a = [0, 0, 0, 1]
        c.new_b_P_b = [0, 0, 0, 1]
        c.root_P_b = [0, 0, 0, 1]
        c.new_b_V_n = [0, 0, 1, 0]
        c.root_V_n = [0, 0, 1, 0]
        return c

    # @profile
    def get_external_collisions(self, joint_name):
        """
        Collisions are saved as a list for each movable robot joint, sorted by contact distance
        :type joint_name: str
        :rtype: SortedKeyList
        """
        if joint_name in self.external_collision:
            return self.external_collision[joint_name]
        return self.default_result

    def get_external_collisions_long_key(self, link_a, body_b, link_b):
        """
        Collisions are saved as a list for each movable robot joint, sorted by contact distance
        :type joint_name: str
        :rtype: SortedKeyList
        """
        return self.external_collision_long_key[link_a, body_b, link_b]

    def get_number_of_external_collisions(self, joint_name):
        return self.number_of_external_collisions[joint_name]

    # @profile
    def get_self_collisions(self, link_a, link_b):
        """
        Make sure that link_a < link_b, the reverse collision is not saved.
        :type link_a: str
        :type link_b: str
        :return:
        :rtype: SortedKeyList
        """
        # FIXME maybe check for reverse key?
        if (link_a, link_b) in self.self_collisions:
            return self.self_collisions[link_a, link_b]
        return self.default_result

    def get_number_of_self_collisions(self, link_a, link_b):
        return self.number_of_self_collisions[link_a, link_b]

    def __contains__(self, item):
        return item in self.self_collisions or item in self.external_collision

    def items(self):
        return self.all_collisions


class BiDict(dict):
    # TODO test me
    def __init__(self, *args, **kwargs):
        super(BiDict, self).__init__(*args, **kwargs)
        self.inverse = {}
        for key, value in self.items():
            self.inverse[value] = key

    def __setitem__(self, key, value):
        if key in self:
            self.inverse[self[key]].remove(key)
        super(BiDict, self).__setitem__(key, value)
        self.inverse[value] = key

    def __delitem__(self, key):
        self.inverse.setdefault(self[key], []).remove(key)
        if self[key] in self.inverse and not self.inverse[self[key]]:
            del self.inverse[self[key]]
        super(BiDict, self).__delitem__(key)


class PrefixName(object):
    def __init__(self, name, prefix, separator='@'):
        self.short_name = name
        self.prefix = prefix
        self.separator = separator
        if prefix:
            self.long_name = '{}{}{}'.format(self.prefix, self.separator, self.short_name)
        else:
            self.long_name = name

    def __str__(self):
        return self.long_name

    def __repr__(self):
        return self.long_name

    def __hash__(self):
        return hash(self.long_name)

    def __eq__(self, other):
        try:
            return other.long_name == self.long_name
        except AttributeError:
            return str(self) == str(other)

    def __ne__(self, other):
        try:
            return other.long_name != self.long_name
        except AttributeError:
            return str(self) != str(other)

    def __le__(self, other):
        try:
            return self.long_name <= other.long_name
        except AttributeError:
            return str(self) <= str(other.long_name)


    def __ge__(self, other):
        try:
            return self.long_name >= other.long_name
        except AttributeError:
            return str(self) >= str(other)

    def __gt__(self, other):
        try:
            return self.long_name > other.long_name
        except AttributeError:
            return str(self) > str(other)

    def __lt__(self, other):
        try:
            return self.long_name < other.long_name
        except AttributeError:
            return str(self) < str(other)

order_map = BiDict({
    0: u'position',
    1: u'velocity',
    2: u'acceleration',
    3: u'jerk',
    4: u'snap',
    5: u'crackle',
    6: u'pop'
})