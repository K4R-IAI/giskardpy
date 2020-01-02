import os
import pickle

import casadi as ca
import numpy as np
from casadi import sign, cos, acos, sin, sqrt, atan2, qpsol
from numpy import pi

from giskardpy import logging
from giskardpy.exceptions import SymengineException
from giskardpy.utils import create_path

pathSeparator = '_'

# VERY_SMALL_NUMBER = 2.22507385851e-308
VERY_SMALL_NUMBER = 1e-100
SMALL_NUMBER = 1e-10

def diag(*args):
    return ca.diag(Matrix(args))

def Symbol(data):
    if isinstance(data, str) or isinstance(data, unicode):
        return ca.SX.sym(data)
    return ca.SX(data)

def jacobian(expressions, symbols):
    return ca.jacobian(expressions, Matrix(symbols))

def equivalent(expression1, expression2):
    return ca.is_equal(ca.simplify(expression1), ca.simplify(expression2), 1)

def free_symbols(expression):
    return ca.symvar(expression)

def is_matrix(expression):
    return hasattr(expression, 'shape') and expression.shape[0] * expression.shape[1] > 1

def is_symbol(expression):
    return expression.shape[0] * expression.shape[1] == 1

def compile_and_execute(f, params):
    # symbols = []
    input = []

    # class next_symbol(object):
    #     symbol_counter = 0
    #
    #     def __call__(self):
    #         self.symbol_counter += 1
    #         return ca.SX.sym('a{}'.format(self.symbol_counter))

    # ns = next_symbol()
    symbol_params = []
    symbol_params2 = []

    for i, param in enumerate(params):
        if isinstance(param, list):
            param = np.array(param)
        if isinstance(param, np.ndarray):
            symbol_param = ca.SX.sym('m', *param.shape)
            if len(param.shape) == 2:
                l = param.shape[0]*param.shape[1]
            else:
                l = param.shape[0]

            input.append(param.reshape((l,1)))
            symbol_params.append(symbol_param)
            asdf = symbol_param.T.reshape((l,1))
            symbol_params2.extend(asdf[k] for k in range(l))
        else:
            # s = ns()
            # symbols.append(s)
            input.append(np.array([param], ndmin=2))
            symbol_param = ca.SX.sym('s')
            symbol_params.append(symbol_param)
            symbol_params2.append(symbol_param)
    # try:
    #     slow_f = Matrix([f(*symbol_params)])
    # except TypeError:
    #     slow_f = Matrix(f(*symbol_params))
    fast_f = speed_up(f(*symbol_params), symbol_params2)
    # subs = {str(symbols[i]): input[i] for i in range(len(symbols))}
    # slow_f.subs()
    input = np.concatenate(input).T[0]
    result = fast_f.call2(input)
    if result.shape[0] * result.shape[1] == 1:
        return result[0][0]
    # if result.shape[0] > 1 and result.shape[1] > 1:
    elif result.shape[1] == 1:
        return result.T[0]
    elif result.shape[0] == 1:
        return result[0]
    else:
        return result


def Matrix(data):
    try:
        return ca.SX(data)
    except NotImplementedError:
        if hasattr(data, u'shape'):
            m = ca.SX(*data.shape)
        else:
            x = len(data)
            if isinstance(data[0], list) or isinstance(data[0], tuple):
                y = len(data[0])
            else:
                y = 1
            m = ca.SX(x, y)
        for i in range(m.shape[0]):
            if y > 1:
                for j in range(m.shape[1]):
                    try:
                        m[i, j] = data[i][j]
                    except:
                        m[i, j] = data[i, j]
            else:
                m[i] = data[i]
        return m


def zeros(x, y):
    return ca.SX.zeros(x, y)


def Abs(x):
    return ca.fabs(x)


def diffable_abs(x):
    """
    :type x: Union[float, Symbol]
    :return: abs(x)
    :rtype: Union[float, Symbol]
    """
    return Abs(x)


def diffable_sign(x):
    """
    !Returns shit if x is very close to but not equal to zero!
    if x > 0:
        return 1
    if x < 0:
        return -1
    if x == 0:
        return 0

    :type x: Union[float, Symbol]
    :return: sign(x)
    :rtype: Union[float, Symbol]
    """
    return ca.sign(x)


# def diffable_heaviside(x):
#     return ca.heaviside(x)


def Max(x, y):
    return ca.fmax(x, y)


def diffable_max_fast(x, y):
    """
    Can be compiled quickly.
    !gets very imprecise if inputs outside of [-1e7,1e7]!
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :return: max(x, y)
    :rtype: Union[float, Symbol]
    """
    return Max(x, y)


def diffable_max(x, y):
    """
    !takes a long time to compile!
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :return: max(x, y)
    :rtype: Union[float, Symbol]
    """
    return Max(x, y)


def Min(x, y):
    return ca.fmin(x, y)


def diffable_min_fast(x, y):
    """
    Can be compiled quickly.
    !gets very imprecise if inputs outside of [-1e7,1e7]!
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :return: min(x, y)
    :rtype: Union[float, Symbol]
    """
    return Min(x, y)


def diffable_min(x, y):
    """
    !takes a long time to compile!
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :return: min(x, y)
    :rtype: Union[float, Symbol]
    """
    return Min(x, y)


def diffable_if_greater_zero(condition, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition > 0 else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater_zero(condition, if_result, else_result)


def diffable_if_greater(a, b, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if a > b else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater(a, b, if_result, else_result)

def if_greater(a, b, if_result, else_result):
    return ca.if_else(ca.gt(a,b), if_result, else_result)

def diffable_if_greater_eq_zero(condition, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition >= 0 else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater_eq_zero(condition, if_result, else_result)


def diffable_if_greater_eq(a, b, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if a >= b else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater_eq(a, b, if_result, else_result)


def diffable_if_eq_zero(condition, if_result, else_result):
    """
    A short expression which can be compiled quickly.
    !Returns shit if condition is very close to but not equal to zero!
    !Returns shit if if_result is outside of [-1e8,1e8]!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition == 0 else else_result
    :rtype: Union[float, Symbol]
    """
    return if_eq_zero(condition, if_result, else_result)


def diffable_if_eq(a, b, if_result, else_result):
    """
    A short expression which can be compiled quickly.
    !Returns shit if condition is very close to but not equal to zero!
    !Returns shit if if_result is outside of [-1e8,1e8]!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if a == b else else_result
    :rtype: Union[float, Symbol]
    """
    return if_eq(a, b, if_result, else_result)


def if_greater_zero(condition, if_result, else_result):
    """
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition > 0 else else_result
    :rtype: Union[float, Symbol]
    """
    _condition = sign(condition)  # 1 or -1
    _if = Max(0, _condition) * if_result  # 0 or if_result
    _else = -Min(0, _condition) * else_result  # 0 or else_result
    return _if + _else + (1 - Abs(_condition)) * else_result  # if_result or else_result


def if_greater_eq_zero(condition, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition >= 0 else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater_eq(condition, 0, if_result, else_result)


def if_greater_eq(a, b, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type a: Union[float, Symbol]
    :type b: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if a >= b else else_result
    :rtype: Union[float, Symbol]
    """
    return ca.if_else(ca.ge(a,b), if_result, else_result)


def if_less_eq(a, b, if_result, else_result):
    """
    !takes a long time to compile!
    !Returns shit if condition is very close to but not equal to zero!
    :type a: Union[float, Symbol]
    :type b: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if a <= b else else_result
    :rtype: Union[float, Symbol]
    """
    return if_greater_eq(b, a, else_result, if_result)


def if_eq_zero(condition, if_result, else_result):
    """
    A short expression which can be compiled quickly.
    :type condition: Union[float, Symbol]
    :type if_result: Union[float, Symbol]
    :type else_result: Union[float, Symbol]
    :return: if_result if condition == 0 else else_result
    :rtype: Union[float, Symbol]
    """
    return ca.if_else(condition, else_result, if_result)


def if_eq(a, b, if_result, else_result):
    return ca.if_else(ca.eq(a,b), if_result, else_result)


def safe_compiled_function(f, file_name):
    create_path(file_name)
    with open(file_name, 'w') as file:
        pickle.dump(f, file)
        logging.loginfo(u'saved {}'.format(file_name))


def load_compiled_function(file_name):
    if os.path.isfile(file_name):
        try:
            with open(file_name, u'r') as file:
                fast_f = pickle.load(file)
                return fast_f
        except EOFError as e:
            os.remove(file_name)
            logging.logerr(u'{} deleted because it was corrupted'.format(file_name))


class CompiledFunction(object):
    def __init__(self, str_params, fast_f, l, shape):
        self.str_params = str_params
        self.fast_f = fast_f
        self.shape = shape
        self.buf, self.f_eval = fast_f.buffer()
        self.out = np.zeros(self.shape, order='F')
        self.buf.set_res(0, memoryview(self.out))

    def __call__(self, **kwargs):
        filtered_args = [kwargs[k] for k in self.str_params]
        return self.call2(filtered_args)

    def call2(self, filtered_args):
        """
        :param filtered_args: parameter values in the same order as in self.str_params
        :type filtered_args: list
        :return:
        """

        filtered_args = np.array(filtered_args, dtype=float)
        self.buf.set_arg(0, memoryview(filtered_args))
        self.f_eval()
        return self.out

def speed_up(function, parameters, backend=u'clang'):
    str_params = [str(x) for x in parameters]
    try:
        f = ca.Function('f', [Matrix(parameters)], [ca.densify(function)])
    except:
        # try:
        f = ca.Function('f', [Matrix(parameters)], ca.densify(function))
        # except:
        #     f = ca.Function('f', parameters, [ca.densify(function)])
    return CompiledFunction(str_params, f, 0, function.shape)


def cross(u, v):
    """
    :param u: 1d matrix
    :type u: Matrix
    :param v: 1d matrix
    :type v: Matrix
    :return: 1d Matrix. If u and v have length 4, it ignores the last entry and adds a zero to the result.
    :rtype: Matrix
    """
    return ca.cross(u, v)


def vector3(x, y, z):
    """
    :param x: Union[float, Symbol]
    :param y: Union[float, Symbol]
    :param z: Union[float, Symbol]
    :rtype: Matrix
    """
    return Matrix([x, y, z, 0])


def point3(x, y, z):
    """
    :param x: Union[float, Symbol]
    :param y: Union[float, Symbol]
    :param z: Union[float, Symbol]
    :rtype: Matrix
    """
    return Matrix([x, y, z, 1])


def norm(v):
    """
    :type v: Matrix
    :return: |v|_2
    :rtype: Union[float, Symbol]
    """
    return ca.norm_2(v)


def scale(v, a):
    """
    :type v: Matrix
    :type a: Union[float, Symbol]
    :rtype: Matrix
    """
    return save_division(v, norm(v)) * a


def dot(*matrices):
    """
    :type a: Matrix
    :type b: Matrix
    :rtype: Union[float, Symbol]
    """
    return ca.mtimes(matrices)


def translation3(x, y, z):
    """
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :return: 4x4 Matrix
        [[1,0,0,x],
         [0,1,0,y],
         [0,0,1,z],
         [0,0,0,1]]
    :rtype: Matrix
    """
    r = eye(4)
    r[0, 3] = x
    r[1, 3] = y
    r[2, 3] = z
    return r


def rotation_matrix_from_rpy(roll, pitch, yaw):
    """
    Conversion of roll, pitch, yaw to 4x4 rotation matrix according to:
    https://github.com/orocos/orocos_kinematics_dynamics/blob/master/orocos_kdl/src/frames.cpp#L167
    :type roll: Union[float, Symbol]
    :type pitch: Union[float, Symbol]
    :type yaw: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    # TODO don't split this into 3 matrices

    rx = Matrix([[1, 0, 0, 0],
                [0, ca.cos(roll), -ca.sin(roll), 0],
                [0, ca.sin(roll), ca.cos(roll), 0],
                [0, 0, 0, 1]])
    ry = Matrix([[ca.cos(pitch), 0, ca.sin(pitch), 0],
                [0, 1, 0, 0],
                [-ca.sin(pitch), 0, ca.cos(pitch), 0],
                [0, 0, 0, 1]])
    rz = Matrix([[ca.cos(yaw), -ca.sin(yaw), 0, 0],
                [ca.sin(yaw), ca.cos(yaw), 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1]])
    return dot(rz,ry,rx)


def rotation_matrix_from_axis_angle(axis, angle):
    """
    Conversion of unit axis and angle to 4x4 rotation matrix according to:
    http://www.euclideanspace.com/maths/geometry/rotations/conversions/angleToMatrix/index.htm
    :param axis: 3x1 Matrix
    :type axis: Matrix
    :type angle: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    ct = ca.cos(angle)
    st = ca.sin(angle)
    vt = 1 - ct
    m_vt_0 = vt * axis[0]
    m_vt_1 = vt * axis[1]
    m_vt_2 = vt * axis[2]
    m_st_0 = axis[0] * st
    m_st_1 = axis[1] * st
    m_st_2 = axis[2] * st
    m_vt_0_1 = m_vt_0 * axis[1]
    m_vt_0_2 = m_vt_0 * axis[2]
    m_vt_1_2 = m_vt_1 * axis[2]
    return Matrix([[ct + m_vt_0 * axis[0], -m_st_2 + m_vt_0_1, m_st_1 + m_vt_0_2, 0],
                  [m_st_2 + m_vt_0_1, ct + m_vt_1 * axis[1], -m_st_0 + m_vt_1_2, 0],
                  [-m_st_1 + m_vt_0_2, m_st_0 + m_vt_1_2, ct + m_vt_2 * axis[2], 0],
                  [0, 0, 0, 1]])


def rotation_matrix_from_quaternion(x, y, z, w):
    """
    Unit quaternion to 4x4 rotation matrix according to:
    https://github.com/orocos/orocos_kinematics_dynamics/blob/master/orocos_kdl/src/frames.cpp#L167
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :type w: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    x2 = x * x
    y2 = y * y
    z2 = z * z
    w2 = w * w
    return Matrix([[w2 + x2 - y2 - z2, 2 * x * y - 2 * w * z, 2 * x * z + 2 * w * y, 0],
                  [2 * x * y + 2 * w * z, w2 - x2 + y2 - z2, 2 * y * z - 2 * w * x, 0],
                  [2 * x * z - 2 * w * y, 2 * y * z + 2 * w * x, w2 - x2 - y2 + z2, 0],
                  [0, 0, 0, 1]])


def frame_axis_angle(x, y, z, axis, angle):
    """
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :param axis: 3x1 Matrix
    :type axis: Matrix
    :type angle: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    return dot(translation3(x, y, z), rotation_matrix_from_axis_angle(axis, angle))


def frame_rpy(x, y, z, roll, pitch, yaw):
    """
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :type roll: Union[float, Symbol]
    :type pitch: Union[float, Symbol]
    :type yaw: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    return dot(translation3(x, y, z), rotation_matrix_from_rpy(roll, pitch, yaw))


def frame_quaternion(x, y, z, qx, qy, qz, qw):
    """
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :type qx: Union[float, Symbol]
    :type qy: Union[float, Symbol]
    :type qz: Union[float, Symbol]
    :type qw: Union[float, Symbol]
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    return dot(translation3(x, y, z), rotation_matrix_from_quaternion(qx, qy, qz, qw))


def eye(size):
    return ca.SX.eye(size)


def inverse_frame(frame):
    """
    :param frame: 4x4 Matrix
    :type frame: Matrix
    :return: 4x4 Matrix
    :rtype: Matrix
    """
    inv = eye(4)
    inv[:3, :3] = frame[:3, :3].T
    inv[:3, 3] = dot(-inv[:3, :3], frame[:3, 3])
    return inv


def position_of(frame):
    """
    :param frame: 4x4 Matrix
    :type frame: Matrix
    :return: 4x1 Matrix; the translation part of a frame in form of a point
    :rtype: Matrix
    """
    return frame[:4, 3:]


def translation_of(frame):
    """
    :param frame: 4x4 Matrix
    :type frame: Matrix
    :return: 4x4 Matrix; sets the rotation part of a frame to identity
    :rtype: Matrix
    """
    r = eye(4)
    r[0, 3] = frame[0, 3]
    r[1, 3] = frame[1, 3]
    r[2, 3] = frame[2, 3]
    return r


def rotation_of(frame):
    """
    :param frame: 4x4 Matrix
    :type frame: Matrix
    :return: 4x4 Matrix; sets the translation part of a frame to 0
    :rtype: Matrix
    """
    frame[0,3] = 0
    frame[1,3] = 0
    frame[2,3] = 0
    return frame


def trace(matrix):
    """
    :type matrix: Matrix
    :rtype: Union[float, Symbol]
    """
    return sum(matrix[i, i] for i in range(matrix.shape[0]))


def rotation_distance(a_R_b, a_R_c):
    """
    :param a_R_b: 4x4 or 3x3 Matrix
    :type a_R_b: Matrix
    :param a_R_c: 4x4 or 3x3 Matrix
    :type a_R_c: Matrix
    :return: angle of axis angle representation of b_R_c
    :rtype: Union[float, Symbol]
    """
    difference = dot(a_R_b.T, a_R_c)
    angle = (trace(difference[:3, :3]) - 1) / 2
    angle = Min(angle, 1)
    angle = Max(angle, -1)
    return acos(angle)


def diffable_axis_angle_from_matrix(rotation_matrix):
    """
    MAKE SURE MATRIX IS NORMALIZED
    :param rotation_matrix: 4x4 or 3x3 Matrix
    :type rotation_matrix: Matrix
    :return: 3x1 Matrix, angle
    :rtype: (Matrix, Union[float, Symbol])
    """
    # TODO nan if angle 0
    # TODO buggy when angle == pi
    # TODO use 'if' to make angle always positive?
    rm = rotation_matrix
    angle = (trace(rm[:3, :3]) - 1) / 2
    angle = acos(angle)
    x = (rm[2, 1] - rm[1, 2])
    y = (rm[0, 2] - rm[2, 0])
    z = (rm[1, 0] - rm[0, 1])
    n = sqrt(x * x + y * y + z * z)

    axis = Matrix([x / n, y / n, z / n])
    return axis, angle


def diffable_axis_angle_from_matrix_stable(rotation_matrix):
    """
    :param rotation_matrix: 4x4 or 3x3 Matrix
    :type rotation_matrix: Matrix
    :return: 3x1 Matrix, angle
    :rtype: (Matrix, Union[float, Symbol])
    """
    # TODO buggy when angle == pi
    rm = rotation_matrix
    angle = (trace(rm[:3, :3]) - 1) / 2
    angle = diffable_min_fast(angle, 1)
    angle = diffable_max_fast(angle, -1)
    angle = acos(angle)
    x = (rm[2, 1] - rm[1, 2])
    y = (rm[0, 2] - rm[2, 0])
    z = (rm[1, 0] - rm[0, 1])
    n = sqrt(x * x + y * y + z * z)
    m = diffable_if_eq_zero(n, 1, n)
    axis = Matrix([diffable_if_eq_zero(n, 0, x / m),
                   diffable_if_eq_zero(n, 0, y / m),
                   diffable_if_eq_zero(n, 1, z / m)])
    return axis, angle


def axis_angle_from_matrix(rotation_matrix):
    """
    :param rotation_matrix: 4x4 or 3x3 Matrix
    :type rotation_matrix: Matrix
    :return: 3x1 Matrix, angle
    :rtype: (Matrix, Union[float, Symbol])
    """
    rm = rotation_matrix
    angle = (trace(rm[:3, :3]) - 1) / 2
    angle = Min(angle, 1)
    angle = Max(angle, -1)
    angle = acos(angle)
    x = (rm[2, 1] - rm[1, 2])
    y = (rm[0, 2] - rm[2, 0])
    z = (rm[1, 0] - rm[0, 1])
    n = sqrt(x * x + y * y + z * z)
    m = if_eq_zero(n, 1, n)
    axis = Matrix([if_eq_zero(n, 0, x / m),
                   if_eq_zero(n, 0, y / m),
                   if_eq_zero(n, 1, z / m)])
    sign = if_eq_zero(angle, 1, diffable_sign(angle))
    axis *= sign
    angle = sign * angle
    return axis, angle


def axis_angle_from_quaternion(x, y, z, w):
    """
    :type x: Union[float, Symbol]
    :type y: Union[float, Symbol]
    :type z: Union[float, Symbol]
    :type w: Union[float, Symbol]
    :return: 4x1 Matrix
    :rtype: Matrix
    """
    l = norm(Matrix([x, y, z, w]))
    x, y, z, w = x / l, y / l, z / l, w / l
    w2 = sqrt(1 - w ** 2)
    angle = (2 * acos(Min(Max(-1, w), 1)))
    m = if_eq_zero(w2, 1, w2)  # avoid /0
    x = if_eq_zero(w2, 0, x / m)
    y = if_eq_zero(w2, 0, y / m)
    z = if_eq_zero(w2, 1, z / m)
    return Matrix([x, y, z]), angle


def quaternion_from_axis_angle(axis, angle):
    """
    :param axis: 3x1 Matrix
    :type axis: Matrix
    :type angle: Union[float, Symbol]
    :return: 4x1 Matrix
    :rtype: Matrix
    """
    half_angle = angle / 2
    return Matrix([axis[0] * sin(half_angle),
                   axis[1] * sin(half_angle),
                   axis[2] * sin(half_angle),
                   cos(half_angle)])


def axis_angle_from_rpy(roll, pitch, yaw):
    """
    :type roll: Union[float, Symbol]
    :type pitch: Union[float, Symbol]
    :type yaw: Union[float, Symbol]
    :return: 3x1 Matrix, angle
    :rtype: (Matrix, Union[float, Symbol])
    """
    # TODO maybe go over quaternion instead of matrix
    return diffable_axis_angle_from_matrix(rotation_matrix_from_rpy(roll, pitch, yaw))


_EPS = np.finfo(float).eps * 4.0


def rpy_from_matrix(rotation_matrix):
    """
    !takes time to compile!
    :param rotation_matrix: 4x4 Matrix
    :type rotation_matrix: Matrix
    :return: roll, pitch, yaw
    :rtype: (Union[float, Symbol], Union[float, Symbol], Union[float, Symbol])
    """
    i = 0
    j = 1
    k = 2

    cy = sqrt(rotation_matrix[i, i] * rotation_matrix[i, i] + rotation_matrix[j, i] * rotation_matrix[j, i])
    if0 = cy - _EPS
    ax = diffable_if_greater_zero(if0,
                                  atan2(rotation_matrix[k, j], rotation_matrix[k, k]),
                                  atan2(-rotation_matrix[j, k], rotation_matrix[j, j]))
    ay = diffable_if_greater_zero(if0,
                                  atan2(-rotation_matrix[k, i], cy),
                                  atan2(-rotation_matrix[k, i], cy))
    az = diffable_if_greater_zero(if0,
                                  atan2(rotation_matrix[j, i], rotation_matrix[i, i]),
                                  0)
    return ax, ay, az


def quaternion_from_rpy(roll, pitch, yaw):
    """
    :type roll: Union[float, Symbol]
    :type pitch: Union[float, Symbol]
    :type yaw: Union[float, Symbol]
    :return: 4x1 Matrix
    :type: Matrix
    """
    roll_half = roll / 2.0
    pitch_half = pitch / 2.0
    yaw_half = yaw / 2.0

    c_roll = cos(roll_half)
    s_roll = sin(roll_half)
    c_pitch = cos(pitch_half)
    s_pitch = sin(pitch_half)
    c_yaw = cos(yaw_half)
    s_yaw = sin(yaw_half)

    cc = c_roll * c_yaw
    cs = c_roll * s_yaw
    sc = s_roll * c_yaw
    ss = s_roll * s_yaw

    x = c_pitch * sc - s_pitch * cs
    y = c_pitch * ss + s_pitch * cc
    z = c_pitch * cs - s_pitch * sc
    w = c_pitch * cc + s_pitch * ss

    return Matrix([x, y, z, w])


def quaternion_from_matrix(matrix):
    """
    !takes a loooong time to compile!
    :param matrix: 4x4 or 3x3 Matrix
    :type matrix: Matrix
    :return: 4x1 Matrix
    :rtype: Matrix
    """
    # return quaternion_from_axis_angle(*diffable_axis_angle_from_matrix_stable(matrix))
    # return quaternion_from_rpy(*rpy_from_matrix(matrix))
    q = Matrix([0, 0, 0, 0])
    if isinstance(matrix, np.ndarray):
        M = Matrix(matrix.tolist())
    else:
        M = Matrix(matrix)
    t = trace(M)

    if0 = t - M[3, 3]

    if1 = M[1, 1] - M[0, 0]

    m_i_i = diffable_if_greater_zero(if1, M[1, 1], M[0, 0])
    m_i_j = diffable_if_greater_zero(if1, M[1, 2], M[0, 1])
    m_i_k = diffable_if_greater_zero(if1, M[1, 0], M[0, 2])

    m_j_i = diffable_if_greater_zero(if1, M[2, 1], M[1, 0])
    m_j_j = diffable_if_greater_zero(if1, M[2, 2], M[1, 1])
    m_j_k = diffable_if_greater_zero(if1, M[2, 0], M[1, 2])

    m_k_i = diffable_if_greater_zero(if1, M[0, 1], M[2, 0])
    m_k_j = diffable_if_greater_zero(if1, M[0, 2], M[2, 1])
    m_k_k = diffable_if_greater_zero(if1, M[0, 0], M[2, 2])

    if2 = M[2, 2] - m_i_i

    m_i_i = diffable_if_greater_zero(if2, M[2, 2], m_i_i)
    m_i_j = diffable_if_greater_zero(if2, M[2, 0], m_i_j)
    m_i_k = diffable_if_greater_zero(if2, M[2, 1], m_i_k)

    m_j_i = diffable_if_greater_zero(if2, M[0, 2], m_j_i)
    m_j_j = diffable_if_greater_zero(if2, M[0, 0], m_j_j)
    m_j_k = diffable_if_greater_zero(if2, M[0, 1], m_j_k)

    m_k_i = diffable_if_greater_zero(if2, M[1, 2], m_k_i)
    m_k_j = diffable_if_greater_zero(if2, M[1, 0], m_k_j)
    m_k_k = diffable_if_greater_zero(if2, M[1, 1], m_k_k)

    t = diffable_if_greater_zero(if0, t, m_i_i - (m_j_j + m_k_k) + M[3, 3])
    q[0] = diffable_if_greater_zero(if0, M[2, 1] - M[1, 2],
                                    diffable_if_greater_zero(if2, m_i_j + m_j_i,
                                                             diffable_if_greater_zero(if1, m_k_i + m_i_k, t)))
    q[1] = diffable_if_greater_zero(if0, M[0, 2] - M[2, 0],
                                    diffable_if_greater_zero(if2, m_k_i + m_i_k,
                                                             diffable_if_greater_zero(if1, t, m_i_j + m_j_i)))
    q[2] = diffable_if_greater_zero(if0, M[1, 0] - M[0, 1],
                                    diffable_if_greater_zero(if2, t, diffable_if_greater_zero(if1, m_i_j + m_j_i,
                                                                                              m_k_i + m_i_k)))
    q[3] = diffable_if_greater_zero(if0, t, m_k_j - m_j_k)

    q *= 0.5 / sqrt(t * M[3, 3])
    return q


def quaternion_multiply(q1, q2):
    """
    :param q1: 4x1 Matrix
    :type q1: Matrix
    :param q2: 4x1 Matrix
    :type q2: Matrix
    :return: 4x1 Matrix
    :rtype: Matrix
    """
    x0 = q2[0]
    y0 = q2[1]
    z0 = q2[2]
    w0 = q2[3]
    x1 = q1[0]
    y1 = q1[1]
    z1 = q1[2]
    w1 = q1[3]
    return Matrix([x1 * w0 + y1 * z0 - z1 * y0 + w1 * x0,
                   -x1 * z0 + y1 * w0 + z1 * x0 + w1 * y0,
                   x1 * y0 - y1 * x0 + z1 * w0 + w1 * z0,
                   -x1 * x0 - y1 * y0 - z1 * z0 + w1 * w0])


def quaternion_conjugate(quaternion):
    """
    :param quaternion: 4x1 Matrix
    :type quaternion: Matrix
    :return: 4x1 Matrix
    :rtype: Matrix
    """
    return Matrix([-quaternion[0], -quaternion[1], -quaternion[2], quaternion[3]])


def quaternion_diff(q0, q1):
    """
    :param q0: 4x1 Matrix
    :type q0: Matrix
    :param q1: 4x1 Matrix
    :type q1: Matrix
    :return: 4x1 Matrix p, such that q1*p=q2
    :rtype: Matrix
    """
    return quaternion_multiply(quaternion_conjugate(q0), q1)


def cosine_distance(v0, v1):
    """
    :param v0: nx1 Matrix
    :type v0: Matrix
    :param v1: nx1 Matrix
    :type v1: Matrix
    :rtype: Union[float, Symbol]
    """
    return 1 - (dot(v0.T, v1))[0]


def euclidean_distance(v1, v2):
    """
    :param v1: nx1 Matrix
    :type v1: Matrix
    :param v2: nx1 Matrix
    :type v2: Matrix
    :rtype: Union[float, Symbol]
    """
    return norm(v1 - v2)


# def floor(a):
#     a += VERY_SMALL_NUMBER
#     return (a - 0.5) - (sp.atan(sp.tan(np.pi * (a - 0.5)))) / (pi)


def fmod(a, b):
    return ca.fmod(a, b)


def normalize_angle_positive(angle):
    """
    Normalizes the angle to be 0 to 2*pi
    It takes and returns radians.
    """
    return fmod(fmod(angle, 2.0 * pi) + 2.0 * pi, 2.0 * pi)


def normalize_angle(angle):
    """
    Normalizes the angle to be -pi to +pi
    It takes and returns radians.
    """
    a = normalize_angle_positive(angle)
    return diffable_if_greater(a, pi, a - 2.0 * pi, a)
    # return Piecewise([, a > pi], [a, True])


def shortest_angular_distance(from_angle, to_angle):
    """
    Given 2 angles, this returns the shortest angular
    difference.  The inputs and ouputs are of course radians.

    The result would always be -pi <= result <= pi. Adding the result
    to "from" will always get you an equivelent angle to "to".
    """
    return normalize_angle(to_angle - from_angle)


def diffable_slerp(q1, q2, t):
    """
    !takes a long time to compile!
    :param q1: 4x1 Matrix
    :type q1: Matrix
    :param q2: 4x1 Matrix
    :type q2: Matrix
    :param t: float, 0-1
    :type t:  Union[float, Symbol]
    :return: 4x1 Matrix; Return spherical linear interpolation between two quaternions.
    :rtype: Matrix
    """
    cos_half_theta = dot(q1.T, q2)

    if0 = -cos_half_theta
    q2 = diffable_if_greater_zero(if0, -q2, q2)
    cos_half_theta = diffable_if_greater_zero(if0, -cos_half_theta, cos_half_theta)

    if1 = diffable_abs(cos_half_theta) - 1.0

    # enforce acos(x) with -1 < x < 1
    cos_half_theta = diffable_min_fast(1, cos_half_theta)
    cos_half_theta = diffable_max_fast(-1, cos_half_theta)

    half_theta = acos(cos_half_theta)

    sin_half_theta = sqrt(1.0 - cos_half_theta * cos_half_theta)
    if2 = 0.001 - diffable_abs(sin_half_theta)

    ratio_a = save_division(sin((1.0 - t) * half_theta), sin_half_theta)
    ratio_b = save_division(sin(t * half_theta), sin_half_theta)
    return diffable_if_greater_eq_zero(if1,
                                       Matrix(q1),
                                       diffable_if_greater_zero(if2,
                                                                0.5 * q1 + 0.5 * q2,
                                                                ratio_a * q1 + ratio_b * q2))


# def piecewise_matrix(*piecewise_vector):
#     # TODO testme
#     # FIXME support non 2d matrices?
#     dimensions = piecewise_vector[0][0].shape
#     for m, condition in piecewise_vector:
#         assert m.shape == dimensions
#     matrix = zeros(*dimensions)
#     for x in range(dimensions[0]):
#         for y in range(dimensions[1]):
#             piecewise_entry = []
#             for m, condition in piecewise_vector:
#                 piecewise_entry.append([m[x, y], condition])
#             matrix[x, y] = Piecewise(*piecewise_entry)
#     return matrix


# def slerp(q1, q2, t):
#     """
#     !takes a long time to compile!
#     :param q1: 4x1 Matrix
#     :type q1: Matrix
#     :param q2: 4x1 Matrix
#     :type q2: Matrix
#     :param t: float, 0-1
#     :type t:  Union[float, Symbol]
#     :return: 4x1 Matrix; Return spherical linear interpolation between two quaternions.
#     :rtype: Matrix
#     """
#     #FIXME
#     d = dot(q1, q2)
#     d_abs = Abs(d)
#     q1_2 = piecewise_matrix([-q1, d < 0.0], [q1, True])
#     angle = acos(d_abs)
#
#     isin = 1.0 / sin(angle)
#     q1_3 = q1_2 * sin((1.0 - t) * angle) * isin
#     q2_2 = q2 * sin(t * angle) * isin
#     q1_3 += q2_2
#     return piecewise_matrix([q1, t == 0.0],
#                             [q2, t == 1.0],
#                             [q1, Abs(d_abs - 1.0) < _EPS],
#                             [q1_2, Abs(angle) < _EPS],
#                             [q1_3, True])

def to_numpy(matrix):
    return np.array(matrix.tolist()).astype(float).reshape(matrix.shape)


def save_division(nominator, denominator, if_nan=0):
    save_denominator = if_eq_zero(denominator, 1, denominator)
    return nominator * if_eq_zero(denominator, if_nan, 1 / save_denominator)


def entrywise_product(matrix1, matrix2):
    """
    :type matrix1: se.Matrix
    :type matrix2: se.Matrix
    :return:
    """
    assert matrix1.shape == matrix2.shape
    result = zeros(*matrix1.shape)
    for i in range(matrix1.shape[0]):
        for j in range(matrix1.shape[1]):
            result[i, j] = matrix1[i, j] * matrix2[i, j]
    return result
