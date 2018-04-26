import torch
from torch import optim, cuda
import pdb
import math
import csv
import pdb
import numpy as np
import pickle
from numpy import genfromtxt

from collections import defaultdict, deque
from struct_to_spn import *
from timeit import default_timer as timer

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from TorchSPN.src import network, param, nodes
from train_mnist import *

print("Loading data set..")
test_raw = genfromtxt('mnist/dataset/mnist_test.csv', delimiter=',')

def segment_data():
    segmented_data = []
    for i in range(10):
        i_examples = test_raw[test_raw[:,0] == i][:,1:] / 255
        segmented_data.append(i_examples)

    return segmented_data

print("Segmenting...")
segmented_data = segment_data()
print("Dataset loaded!")

model = pickle.load(open('spn_0', 'rb'))

num_tests = 100
error = 0
for test_i in range(num_tests):
    for digit in range(10):
        num_tests += 1
        data = segment_data[digit][test_i]
        y_pred = model.classify_data(data)
        if (model.digit == digit) != y_pred:
            error += 1

pdb.set_trace()
