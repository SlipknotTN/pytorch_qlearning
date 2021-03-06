"""
Train script of the Deep Q-Learning agent
Generic reference: https://pytorch.org/tutorials/intermediate/reinforcement_q_learning.html

Other ideas: https://gsurma.medium.com/atari-reinforcement-learning-in-depth-part-1-ddqn-ceaa762a546f

TODO/Insights/Ideas:
- Solve system out of memory -> Temporary fix https://github.com/openai/gym/pull/2096
- We want to learn to turn, probably we should "cluster" the states and avoid duplicates/similarity.
  Or possible augmentations like train with mirrored images, but we have to mirror left/right action
- Update experience buffer in a smarter way. Not FIFO only in time. We should build a diverse experience buffer.
  By replacing the old experience we also wipe out the pre-recorded experience very fast.
  Easier maybe to just increase the experience buffer size. UPDATE: increasing the experience size improved the results.
- Try skip frames.
- Analyze recorded experience, we need to skip more at the beginning?
- After 500-600 episodes the agent degrades. Is the new experience useless? Do we have to store more old experience?
  Do we have to investigate better from 400 to 500 (maybe higher save frequency?)
"""
import argparse
import os
import pickle
import shutil

import cv2
import gym
import numpy as np
import torch
import torch.optim as optim
from torch import nn
from tensorboardX import SummaryWriter

from qlearning.common.env_interaction import take_most_probable_action
from qlearning.common.input_processing import get_input_tensor_list
from qlearning.common.space import get_encoded_actions, get_continuous_actions
from qlearning.common.experience_buffer import ExperienceBuffer
from qlearning.common.input_states import InputStates
from qlearning.common.config import ConfigParams
from qlearning.model.model_factory import ModelFactory


def run_validation_episode(env, config, model, available_actions, env_render=True, debug_state=False) -> float:
    """
    Run a validation episode taking the most probable action at every step
    """
    total_reward = 0.0
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
    while not done:
        done, next_state, reward = take_most_probable_action(env, input_states, model, available_actions)
        if env_render:
            env.render()

        # Update the input states
        input_states.add_state(next_state)
        if debug_state:
            last_frame_bw = input_states.get_last_bw_frame()
            cv2.imshow("Validation State", last_frame_bw)
            cv2.waitKey(1)

        # Update the episode reward
        total_reward += reward

    return total_reward


def do_parsing():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description="Q-Learning PyTorch training script")
    parser.add_argument("--config_file", required=True, type=str, help="Output dir for training artifacts")
    parser.add_argument("--output_dir", required=True, type=str, help="Output directory ")
    parser.add_argument("--initial_experience_file", required=False, type=str,
                        help="Prerecorded experience to start with")
    parser.add_argument("--env_render", action="store_true", help="Render environment in GUI")
    parser.add_argument("--debug_state", action="store_true", help="Show last state frame in GUI")
    parser.add_argument("--save_experience", action="store_true",
                        help="Save experience memory for future analysis, "
                             "current experience file is overwritten at every step")
    args = parser.parse_args()
    return args


def main():
    args = do_parsing()
    print(args)

    config = ConfigParams(args.config_file)

    env = gym.make('CarRacing-v0')

    os.makedirs(args.output_dir, exist_ok=True)
    shutil.copy(args.config_file, os.path.join(args.output_dir, "config.cfg"))

    available_actions = get_encoded_actions(config.action_complexity)
    train_model = ModelFactory.create_model(
        architecture=config.architecture,
        input_size=env.observation_space.shape[0],
        input_frames=config.input_num_frames,
        output_size=len(available_actions)
    )
    print(train_model)
    train_model.cuda()
    train_model.train()

    # Target model aligned periodically to train model, fixed Q-target technique
    target_model = ModelFactory.create_model(
        architecture=config.architecture,
        input_size=env.observation_space.shape[0],
        input_frames=config.input_num_frames,
        output_size=len(available_actions)
    )
    target_model.load_state_dict(train_model.state_dict())
    target_model.cuda()
    target_model.eval()

    criterion = nn.MSELoss()
    optimizer = optim.Adam(train_model.parameters(), lr=config.alpha)

    # Experience buffer
    experience_buffer = ExperienceBuffer(max_size=config.experience_buffer_size)
    if args.initial_experience_file:
        print(f"Loading experience buffer from {args.initial_experience_file}, "
              f"it is up to you to assert that number of input frames and action space are coherent with the train")
        assert(os.path.exists(args.initial_experience_file)), \
            f"Experience file {args.initial_experience_file} not exists"
        with open(args.initial_experience_file, "rb") as in_fp:
            loaded_experience_buffer = pickle.load(in_fp)
            assert loaded_experience_buffer.size <= config.experience_buffer_size, \
                f"Loaded experience is bigger then config value " \
                f"{experience_buffer.size} vs {config.experience_buffer_size}"
            # Update the experience buffer to use
            experience_buffer.from_experience_buffer(loaded_experience_buffer)
            print(f"Experience max size: {experience_buffer.max_size}, loaded size: {experience_buffer.size}")
            del loaded_experience_buffer

    # TensorBoardX writer
    writer = SummaryWriter(args.output_dir, comment=os.path.basename(args.config_file[:-4]))

    try:

        for num_episode in range(0, config.num_episodes):

            total_reward = 0.0
            losses = []
            print(f"\nStart episode {num_episode + 1}")
            epsilon = config.min_epsilon + (config.initial_epsilon - config.min_epsilon) * np.exp(-config.eps_decay_rate * num_episode)
            print(f"Epsilon: {epsilon}")
            print(f"Experience buffer length: {experience_buffer.size}")
            state = env.reset()

            # Update TensorBoard
            writer.add_scalar("Train/epsilon", epsilon, num_episode + 1)
            writer.add_scalar("Train/experience_size", experience_buffer.size, num_episode + 1)

            # Prepare starting input states
            input_states = InputStates(config.input_num_frames)
            input_states.add_state(state)
            # Warmup: Fill the input
            for _ in range(0, config.input_num_frames - 1):
                no_action_discrete = available_actions[0]
                no_action = get_continuous_actions(no_action_discrete)
                next_state, reward, done, _ = env.step(no_action)
                input_states.add_state(next_state)

            done = False
            consecutive_negative_rewards = 0
            while not done and consecutive_negative_rewards < config.consecutive_neg_reward_stop:

                # EXPLORATION STEP

                input_tensor_explore = get_input_tensor_list([input_states.as_list()])

                # Choose action from epsilon-greedy policy
                state_action_values_explore = train_model(input_tensor_explore)
                state_action_values_explore_np = state_action_values_explore.cpu().data.numpy()[0]
                if np.random.rand() < epsilon:
                    action_id = np.random.randint(0, len(available_actions))
                else:
                    action_id = np.argmax(state_action_values_explore_np)
                # print(state_action_values_np)
                # Convert to continuous action space
                action_discrete = available_actions[action_id]
                action = get_continuous_actions(action_discrete)

                # Apply action
                next_state, reward, done, _ = env.step(action)
                if args.env_render:
                    env.render()

                # Update consecutive negative reward counter
                if reward >= 0.0:
                    consecutive_negative_rewards = 0
                else:
                    consecutive_negative_rewards += 1

                # Update the input states
                s = input_states.as_list()
                input_states.add_state(next_state)
                s1 = input_states.as_list()
                # Store the experience (s, a, r, s1) if episode not finished.
                # State size is #config.num_input_frames frames.
                if not done:
                    experience_buffer.add([s, action_id, reward, s1])
                if args.debug_state:
                    last_frame_bw = input_states.get_last_bw_frame()
                    cv2.imshow("State", last_frame_bw)
                    cv2.waitKey(1)

                # TRAINING STEP

                # Sample experience
                sampled_experience = experience_buffer.sample(batch_size=config.batch_size)

                # Reshape from list of (s, a, r, s') to list(s), list(a), list(r), list(r')
                state_train, action_train, reward_train, next_state_train, _ = [list(elem) for elem in zip(*sampled_experience)]

                input_tensor_train_1 = get_input_tensor_list(state_train)
                state_action_values_train = train_model(input_tensor_train_1)

                input_tensor_target_2 = get_input_tensor_list(next_state_train)
                next_state_action_values_target = target_model(input_tensor_target_2)

                # Update model weights according to new state and taken action (batch_size is 1)
                # The target is the reward + gamma x max q(new_state, any_action, w)
                reward_train_t_cuda = torch.Tensor(reward_train).cuda()
                target = reward_train_t_cuda + config.gamma * torch.max(next_state_action_values_target, dim=1).values
                # td_error = target - q(state, action, w)
                # Weights update = alfa x td_error x gradient_w.r.t._w(q(state, action, w))
                # With PyTorch we use learning_rate and MSE error
                # calculate the loss between predicted and target class
                # Retrieve the state value for every action taken in the batch
                state_action_values_train_filtered = \
                    torch.cat([state_action_values_train[batch_id][action_id].unsqueeze(0)
                               for batch_id, action_id in enumerate(action_train)], dim=0)

                # Update the weights
                loss = criterion(target, state_action_values_train_filtered)
                losses.append(loss.clone().cpu().data.numpy())
                # Reset the parameters (weights) gradients
                optimizer.zero_grad()
                # backward pass to calculate the weight gradients
                loss.backward()
                # update the weights
                optimizer.step()

                # Update the episode reward
                total_reward += reward

            # END OF EPISODE

            train_avg_loss = np.mean(losses)

            # Update TensorBoard
            writer.add_scalar("Train/loss", train_avg_loss, num_episode + 1)
            writer.add_scalar("Train/reward", total_reward, num_episode + 1)

            print(f"End of episode {num_episode + 1}, total_reward: {total_reward}, avg_loss: {train_avg_loss}")

            # Update target model every episode
            if (num_episode + 1) % config.update_target_frequency == 0:
                print("\nUpdating target model")
                target_model.load_state_dict(train_model.state_dict())

            # Validation, since it runs only one episode and the environment is randomly generated,
            # the single value is not really reliable
            if (num_episode + 1) % config.short_validation_frequency == 0:
                print(f"\nRun single validation episode after {num_episode + 1} episodes")
                train_model.eval()
                val_reward = run_validation_episode(env, config, train_model, available_actions,
                                                    env_render=args.env_render, debug_state=args.debug_state)
                print(f"End of validation episode, total_reward: {val_reward}")
                writer.add_scalar("Validation/reward_single", val_reward, num_episode + 1)
                train_model.train()

            # Longer validation sep
            if (num_episode + 1) % config.long_validation_frequency == 0:
                total_val_reward = 0.0
                train_model.eval()
                for i in range(0, 10):
                    print(f"\nRun long validation after {num_episode + 1} episodes: episode {i+1}/10")
                    val_reward = run_validation_episode(env, config, train_model, available_actions,
                                                        env_render=args.env_render, debug_state=args.debug_state)
                    print(f"End of validation episode, total_reward: {val_reward}")
                    total_val_reward += val_reward
                print(f"\nEnd of long validation after {num_episode + 1} episodes, avg_reward: {total_val_reward/10.0}")
                writer.add_scalar("Validation/reward_avg", total_val_reward/10.0, num_episode + 1)
                train_model.train()

            # Save model
            if (num_episode + 1) % config.save_model_frequency == 0:
                print("\nSaving model")
                torch.save(
                    target_model.state_dict(),
                    os.path.join(args.output_dir, f"model_{num_episode + 1}.pth")
                )

            # Export experience
            if args.save_experience and args.save_experience and experience_buffer.is_full():
                experience_dump_file = f"experience_{experience_buffer.size}.pkl"
                with open(os.path.join(args.output_dir, experience_dump_file), "wb") as out_fp:
                    pickle.dump(experience_buffer, out_fp)
                print(f"\nExperienceBuffer dump saved to \"{experience_dump_file}\"")

    finally:
        writer.close()
        env.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
