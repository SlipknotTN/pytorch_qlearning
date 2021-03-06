"""
Test script to evaluate a trained mode
"""
import argparse
import os

import cv2
import gym
import torch

from qlearning.common.env_interaction import take_most_probable_action
from qlearning.common.space import get_encoded_actions, get_continuous_actions
from qlearning.common.input_states import InputStates
from qlearning.common.config import ConfigParams
from qlearning.model.model_factory import ModelFactory


def do_parsing():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description="Q-Learning PyTorch test script")
    parser.add_argument("--config_file", required=True, type=str,
                        help="Path to the config file used to train the model")
    parser.add_argument("--model_path", required=True, type=str, help="Path to the model path")
    parser.add_argument("--test_episodes", required=True, type=int, help="Number of episodes to run")
    parser.add_argument("--env_render", action="store_true", help="Render environment in GUI")
    parser.add_argument("--debug_state", action="store_true", help="Show last state frame in GUI")
    parser.add_argument("--frames_output_dir", required=False, type=str, help="Path to save frames")
    args = parser.parse_args()
    return args


def main():
    args = do_parsing()
    print(args)

    config = ConfigParams(args.config_file)

    env = gym.make('CarRacing-v0')

    available_actions = get_encoded_actions(config.action_complexity)
    model = ModelFactory.create_model(
        architecture=config.architecture,
        input_size=env.observation_space.shape[0],
        input_frames=config.input_num_frames,
        output_size=len(available_actions)
    )

    model.load_state_dict(torch.load(args.model_path))

    print(model)
    model.cuda()
    model.eval()

    sum_of_episodes_rewards = 0

    if args.frames_output_dir:
        os.makedirs(args.frames_output_dir)

    for num_episode in range(0, args.test_episodes):

        if args.frames_output_dir:
            episode_output_dir = os.path.join(args.frames_output_dir, f"episode_{num_episode + 1}")
            os.makedirs(episode_output_dir)

        total_reward = 0.0
        print(f"Start episode {num_episode + 1}")
        state = env.reset()

        # Prepare starting input states
        input_states = InputStates(config.input_num_frames)
        input_states.add_state(state)
        # Warmup: Fill the input
        for _ in range(0, config.input_num_frames - 1):
            no_action_discrete = available_actions[0]
            no_action = get_continuous_actions(no_action_discrete)
            next_state, reward, done, _ = env.step(no_action)
            input_states.add_state(next_state)

        # Reply the first frame config.input_num_frames times
        done = False
        frame_num = 0
        while not done:
            done, next_state, reward = take_most_probable_action(env, input_states, model, available_actions)
            if args.env_render:
                env.render()

            if args.frames_output_dir:
                cv2.imwrite(os.path.join(episode_output_dir, f"frame_{frame_num + 1}.jpg"),
                            cv2.cvtColor(next_state, cv2.COLOR_RGB2BGR))

            # Update the input states
            input_states.add_state(next_state)
            if args.debug_state:
                last_frame_bw = input_states.get_last_bw_frame()
                cv2.imshow("State", last_frame_bw)
                cv2.waitKey(1)

            # Update the episode reward
            total_reward += reward

            frame_num += 1

        # End of episode, epsilon decay
        sum_of_episodes_rewards += total_reward
        print(f"End of episode {num_episode + 1}, total_reward: {total_reward}\n")

    print(f"Average total rewards over {args.test_episodes} episodes: {sum_of_episodes_rewards/args.test_episodes}")


if __name__ == "__main__":
    main()
