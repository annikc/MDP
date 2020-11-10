# Actor-Critic Model-Free Control Module Object Class and Related Functions
# Written and maintained by Annik Carson
# Last updated: Nov 2020
#
# =====================================
#           IMPORT MODULES            #
# =====================================
from __future__ import division, print_function
import numpy as np

import torch
import torch.nn.functional as F
from torch.autograd import Variable


class ActorCritic(torch.nn.Module):
    def __init__(self, agent_params, **kwargs):
        # call the super-class init
        super(ActorCritic, self).__init__()
        self.input_dims = agent_params['input_dims']
        self.action_dims = agent_params['action_dims']

        if 'rfsize' not in agent_params.keys():
            self.rfsize = kwargs.get('rfsize', 4)
        else:
            self.rfsize = agent_params['rfsize']
        if 'padding' not in agent_params.keys():
            self.padding = kwargs.get('padding', 1)
        else:
            self.padding = agent_params['padding']
        if 'dilation' not in agent_params.keys():
            self.dilation = 1
        else:
            self.dilation = kwargs.get('dilation', 1)
        if 'stride' not in agent_params.keys():
            self.stride = kwargs.get('stride', 1)
        else:
            self.stride = agent_params['stride']
        if 'batch_size' not in agent_params.keys():
            self.batch_size = kwargs.get('batch_size', 1)
        else:
            self.batch_size = agent_params['batch_size']

        if 'gamma' not in agent_params.keys():
            self.gamma = kwargs.get('gamma', 0.98)
        else:
            self.gamma = agent_params['gamma']

        if 'eta' not in agent_params.keys():
            self.eta = kwargs.get('eta', 5e-4)
        else:
            self.eta = agent_params['eta']

        self.use_SR = kwargs.get('use_SR', False)

        if 'hidden_types' in agent_params.keys():
            if len(agent_params['hidden_dims']) != len(agent_params['hidden_types']):
                raise Exception('Incorrect specification of hidden layer dimensions')

            self.hidden_types = agent_params['hidden_types']
            # create lists for tracking hidden layers
            self.hidden = torch.nn.ModuleList()
            self.hidden_dims = agent_params['hidden_dims']

            self.hx = []
            self.cx = []
            # calculate dimensions for each layer
            for ind, htype in enumerate(self.hidden_types):
                if htype not in ['linear', 'lstm', 'gru', 'conv', 'pool']:
                    raise Exception(f'Unrecognized type for hidden layer {ind}')
                if ind == 0:
                    input_d = self.input_dims
                else:
                    if self.hidden_types[ind - 1] in ['conv', 'pool'] and not htype in ['conv', 'pool']:
                        input_d = int(np.prod(self.hidden_dims[ind - 1]))

                    else:
                        input_d = self.hidden_dims[ind - 1]

                if htype in ['conv', 'pool']:
                    output_d = tuple(self.conv_output(input_d))
                    self.hidden_dims[ind] = output_d

                else:
                    output_d = self.hidden_dims[ind]

                # construct the layer
                if htype == 'linear':
                    print('inputd outputd', input_d, output_d)
                    self.hidden.append(torch.nn.Linear(input_d, output_d))
                    self.hx.append(None)
                    self.cx.append(None)
                elif htype == 'lstm':
                    self.hidden.append(torch.nn.LSTMCell(input_d, output_d))
                    self.hx.append(Variable(torch.zeros(self.batch_size, output_d)))
                    self.cx.append(Variable(torch.zeros(self.batch_size, output_d)))
                elif htype == 'gru':
                    self.hidden.append(torch.nn.GRUCell(input_d, output_d))
                    self.hx.append(Variable(torch.zeros(self.batch_size, output_d)))
                    self.cx.append(None)
                elif htype == 'conv':
                    in_channels = input_d[0]
                    out_channels = output_d[0]
                    self.hidden.append(
                        torch.nn.Conv2d(in_channels, out_channels, kernel_size=self.rfsize, padding=self.padding,
                                        stride=self.stride, dilation=self.dilation))
                    self.hx.append(None)
                    self.cx.append(None)
                elif htype == 'pool':
                    self.hidden.append(
                        torch.nn.MaxPool2d(kernel_size=self.rfsize, padding=self.padding, stride=self.stride,
                                           dilation=self.dilation))
                    self.hx.append(None)
                    self.cx.append(None)

            # create the actor and critic layers
            self.layers = [self.input_dims] + self.hidden_dims + [self.action_dims]
            self.output = torch.nn.ModuleList()
            self.output.append(torch.nn.Linear(output_d, self.action_dims))  # actor
            self.output.append(torch.nn.Linear(output_d, 1))  # critic

        else:
            self.layers = [self.input_dims, self.action_dims]
            self.output = torch.nn.ModuleList([
                torch.nn.Linear(self.input_dims, self.action_dims),  # ACTOR
                torch.nn.Linear(self.input_dims, 1)])  # CRITIC
        output_d = self.hidden_dims[-1]

        self.optimizer = torch.optim.Adam(self.parameters(), lr=self.eta)

    def conv_output(self, input_tuple, **kwargs):
        channels, h_in, w_in = input_tuple
        padding = kwargs.get('padding', self.padding)
        dilation = kwargs.get('dilation', self.dilation)
        kernel_size = kwargs.get('rfsize', self.rfsize)
        stride = kwargs.get('stride', self.stride)

        h_out = int(np.floor(((h_in + 2 * padding - dilation * (kernel_size - 1) - 1) / stride) + 1))
        w_out = int(np.floor(((w_in + 2 * padding - dilation * (kernel_size - 1) - 1) / stride) + 1))

        return (channels, h_out, w_out)

    def forward(self, x):
        x = torch.Tensor(x)
        # check the inputs
        if type(self.input_dims) == int:
            assert x.shape[-1] == self.input_dims
        elif type(self.input_dims) == tuple:
            if x.shape[0] == 1:
                assert self.input_dims == tuple(x.shape[1:])  # x.shape[0] is the number of items in the batch
            if not (isinstance(self.hidden[0], torch.nn.Conv2d) or isinstance(self.hidden[0], torch.nn.MaxPool2d)):
                raise Exception(f'image to non {self.hidden[0]} layer')

        # pass the data through each hidden layer
        for i, layer in enumerate(self.hidden):
            # squeeze if last layer was conv/pool and this isn't
            if i > 0:
                if (isinstance(self.hidden[i - 1], torch.nn.Conv2d) or isinstance(self.hidden[i - 1],
                                                                                  torch.nn.MaxPool2d)) and \
                        not (isinstance(layer, torch.nn.Conv2d) or isinstance(layer, torch.nn.MaxPool2d)):
                    x = x.view(x.shape[0], -1)

            # run input through the layer depending on type
            if isinstance(layer, torch.nn.Linear):
                x = F.relu(layer(x))
                if i == (len(self.hidden) - 2):
                    phi = x
                elif i == (len(self.hidden) - 1):
                    psi = x
            elif isinstance(layer, torch.nn.LSTMCell):
                x, cx = layer(x, (self.hx[i], self.cx[i]))
                self.hx[i] = x.clone()
                self.cx[i] = cx.clone()
            elif isinstance(layer, torch.nn.GRUCell):
                x = layer(x, self.hx[i])
                self.hx[i] = x.clone()
            elif isinstance(layer, torch.nn.Conv2d):
                x = F.relu(layer(x))
                self.conv = x
            elif isinstance(layer, torch.nn.MaxPool2d):
                x = layer(x)
        # pass to the output layers
        policy = F.softmax(self.output[0](x), dim=1)
        value = self.output[1](x)
        if self.use_SR:
            return policy, value
        else:
            return policy, value

    def reinit_hid(self):
        # to store a record of the last hidden states
        self.hx = []
        self.cx = []

        for i, layer in enumerate(self.hidden):
            if isinstance(layer, torch.nn.Linear):
                pass
            elif isinstance(layer, torch.nn.LSTMCell):
                self.hx.append(Variable(torch.zeros(self.batch_size, layer.hidden_size)))
                self.cx.append(Variable(torch.zeros(self.batch_size, layer.hidden_size)))
            elif isinstance(layer, torch.nn.GRUCell):
                self.hx.append(Variable(torch.zeros(self.batch_size, layer.hidden_size)))
                self.cx.append(None)
            elif isinstance(layer, torch.nn.Conv2d):
                pass
            elif isinstance(layer, torch.nn.MaxPool2d):
                pass
