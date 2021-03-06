import configparser


class ConfigParams(object):

    def __init__(self, file):

        config = configparser.ConfigParser()
        config.read_file(open(file))

        # Model
        self.batch_size = config.getint("MODEL", "batch_size")
        self.input_num_frames = config.getint("MODEL", "input_num_frames")
        self.action_complexity = config.get("MODEL", "action_complexity")
        self.architecture = config.get("MODEL", "architecture")
        assert self.action_complexity in ["full", "simple", "basic"]

        # Train
        self.consecutive_neg_reward_stop = config.getint("TRAIN", "consecutive_negative_reward_stop", fallback=1000)
        self.experience_buffer_size = config.getint("TRAIN", "experience_buffer_size")
        self.num_episodes = config.getint("TRAIN", "num_episodes")
        self.initial_epsilon = config.getfloat("TRAIN", "initial_epsilon")
        self.min_epsilon = config.getfloat("TRAIN", "min_epsilon")
        self.eps_decay_rate = config.getfloat("TRAIN", "eps_decay_rate")
        self.gamma = config.getfloat("TRAIN", "gamma")
        self.alpha = config.getfloat("TRAIN", "alpha")  # aka learning rate
        # Model checkpoint is saved every #save_model_frequency episodes
        self.save_model_frequency = config.getint("TRAIN", "save_model_frequency")
        # Single validation run is executed every #short_validation_frequency episodes
        self.short_validation_frequency = config.getint("TRAIN", "short_validation_frequency")
        # Longer validation (10 episodes) run is executed every #long_validation_frequency episodes
        self.long_validation_frequency = config.getint("TRAIN", "long_validation_frequency")
        # Target model is updated every #update_target_frequency episodes
        self.update_target_frequency = config.getint("TRAIN", "update_target_frequency")
