from basic.Experiments import Experiment as ex
import numpy as np
import gym
#from basic.Agents.Networks.fcx2 import Network as fcx
from basic.Agents.Networks.annik_ac import ActorCritic as Network
from basic.Agents.EpisodicMemory import EpisodicMemory as Memory
from basic.Agents import Agent
import matplotlib.pyplot as plt

class basic_agent_params():
    def __init__(self, env):
        self.load_model = False
        self.load_dir   = ''
        self.architecture = 'A'
        self.input_dims = 2
        self.action_dims = 3
        self.hidden_types = ['linear', 'linear']
        self.hidden_dims = [40, 40]
        self.freeze_w = False
        self.rfsize = 5
        self.gamma = 0.98
        self.eta = 0.001

env = gym.make('MountainCar-v0')
s = env.reset()
print(env.action_space.n)


agent_params = basic_agent_params(env)
#policy_value_network = fcx(lr=0.06, input_dim=env.observation_space.shape, fc1_dims=30, fc2_dims=30, n_actions=env.action_space.shape)
#agent = Agent(network=policy_value_network)

agent = Agent(network=Network(agent_params.__dict__) )#, memory=Memory(entry_size=env.action_space.n, cache_limit=env.nstates))

run = ex(agent,env)
run.run(1000,300, printfreq=100)
# TODO: loading parameters with yaml file?
# TODO: logging data

print('hello')