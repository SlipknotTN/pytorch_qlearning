from typing import Union, List

import numpy as np

"""Discrete to continuous actions conversion"""
steer_to_continuous = {0: -1.0, 1: 0.0, 2: 1.0}
gas_to_continuous = {0: 0.0, 1: 1.0}
brake_to_continuos = {0: 0.0, 1: 1.0}

"""Single dimension action space mapping """
encoded_actions = {
    0: [0, 0, 0],
    1: [0, 0, 1],
    2: [0, 1, 0],
    3: [0, 1, 1],

    4: [1, 0, 0],
    5: [1, 0, 1],
    6: [1, 1, 0],
    7: [1, 1, 1],

    8: [2, 0, 0],
    9: [2, 0, 1],
    10: [2, 1, 0],
    11: [2, 1, 1],
}


def get_continuous_actions(discrete_actions: Union[np.ndarray, List[int]]) -> np.ndarray:
    """
    Convert from discrete to continuous action space
    Steer: [0, 1, 2] -> [-1.0, 0.0, 1.0]
    Gas: [0, 1] -> [0.0, 1.0]
    Brake: [0, 1] -> [0.0, 1.0]
    :param discrete_actions: actions in the discrete space (integers)
    :return: actions in the continuous space (float)
    """
    steer_cont = steer_to_continuous[discrete_actions[0]]
    gas_cont = gas_to_continuous[discrete_actions[1]]
    brake_cont = brake_to_continuos[discrete_actions[2]]
    return np.asarray([steer_cont, gas_cont, brake_cont])