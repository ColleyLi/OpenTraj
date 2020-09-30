# Author: Juan Baldelomar
# Email: juan.baldelomar@cimat.mx

import numpy as np
import os
import sys
import argparse
import math
import matplotlib.pyplot as plt
from toolkit.core.trajlet import split_trajectories
from toolkit.benchmarking.load_all_datasets import get_trajlets
from toolkit.benchmarking.load_all_datasets import all_dataset_names
from scipy.stats import multivariate_normal
import seaborn as sns
import pandas as pd

from toolkit.loaders.loader_eth import load_eth

# Parser arguments
# parser = argparse.ArgumentParser(description='Measure multimodality'
#                                              'on trajectories.')
# parser.add_argument('--root-path', '--root',
#                     default='C:/verano2020/OpenTraj-master/',
#                     help='path to foldet that contain dataset')
# args = parser.parse_args()
#
# # reference_folders = {'eth-univ': 'datasets/ETH/seq_eth/',
# #                      'eth-hotel': 'datasets/ETH/seq_hotel/',
# #                      'ucy-zara1': 'datasets/UCY/zara01/',
# #                      'ucy-zara2': 'datasets/UCY/zara02/',
# #                      'ucy-univ3': 'datasets/UCY/students03/',
# #                      }
#
# graphics_dir = os.path.join(args.root_path, 'generated_graphics')
# if not os.path.exists(graphics_dir): os.makedirs(graphics_dir)


def Gauss_K(x, y, h):
    N = len(x)
    return math.exp(-np.linalg.norm(x - y) ** 2 / (2 * h ** 2)) / (2 * math.pi * h ** 2) ** N


# separates every trajectory in its observed and predicted trajlets
def obs_pred_trajectories(trajectories, separator=8, f_per_traj=20):
    N_t = len(trajectories)
    Trajm = []
    Trajp = []
    for tr in trajectories:
        Trajm.append(tr[range(separator), :])
        Trajp.append(tr[range(separator, f_per_traj), :])
    return Trajm, Trajp


# Weights for the GMM
def weights(Xm, k, h, Tobs=8, Tpred=12):
    N_t = len(Xm)
    aux = 0
    for l in range(N_t):
        aux += Gauss_K(Xm[k], Xm[l], h)
    w = []
    for l in range(N_t):
        var = Gauss_K(Xm[k], Xm[l], h) / aux
        w.append(var)

    return np.array(w)


def get_sample(Xp, w, M, h, replace=False):
    probabilities = w / np.sum(w)
    if np.count_nonzero(probabilities) > M:
        l_sample = np.random.choice(range(len(Xp)), M, p=probabilities, replace=replace)
    else:
        l_sample = np.random.choice(range(len(Xp)), M, p=probabilities, replace=True)
    sample = []
    for i in l_sample:
        sample.append(Xp[i])
    size = len(Xp[0]) * 2
    cov = h * np.identity(size)

    for i in range(M):
        s = sample[i].reshape(size)
        s = multivariate_normal.rvs(s, cov)
        s = s.reshape(int(size / 2), 2)
        sample[i] = s

    return sample


# Entropy estimation of the kth trajectory ones weights have been gotten
def entropy(Xp, k, h, w, M, replace=False):
    N_t = len(Xp)
    samples = get_sample(Xp, w, M, h, replace=replace)

    H = 0
    for m in range(M):
        aux = 0
        for l in range(N_t):
            aux += w[l] * Gauss_K(samples[m], Xp[l], h)
        if aux <= 1 / 10 ** 320: aux = 1 / 10 ** 320
        H += -math.log(aux)
        H = H / M
    return H


def detect_separator(trajectories, secs):
    traj = trajectories[0]
    for i in range(len(traj)):
        if traj[i, 4] - traj[0, 4] > secs:
            break
    return i - 1


# Visualizing a trajectory and its comparison to others
def visualize_max_entropy(trajs, n, path, name, replace):
    H_path = os.path.join(path, 'H.txt')
    if not os.path.exists(H_path):
        return None
    reference_path = os.path.join(path, 'reference.png')
    H = np.loadtxt(H_path)
    Hinv = np.linalg.inv(H)

    plt.figure(figsize=(10, 10))
    img = plt.imread(reference_path)
    plt.imshow(img)

    for i in range(len(trajs)):
        traj = trajs[i]
        cat = np.vstack([traj[:, 0], traj[:, 1], np.ones_like(traj[:, 0])]).T
        tCat = (Hinv @ cat.T).T

        # Get points in image
        x = tCat[:, 1] / tCat[:, 2]
        y = tCat[:, 0] / tCat[:, 2]
        # if not i == n and i%5 == 0:
        if i == n:
            xn = x
            yn = y
        elif i % 2 == 0:
            plt.plot(x, y, c='blue', linewidth=2)
    plt.plot(xn, yn, c='yellowgreen', linewidth=4)

    if replace == True:
        R = 'R'
    else:
        R = 'NR'
    img_title = graphics_dir + '/' + name + '-max_entropy' + R + '.svg'
    plt.savefig(img_title, format='svg')
    plt.clf()


def get_entropies(opentraj_root, trajectories, dataset_name, M=30, replace=False):
    # Load dataset
    N_t = len(trajectories)

    # Number of frames in observed and predicted trajlets
    Tobs = detect_separator(trajectories, 3.2)
    Tpred = len(trajectories[0]) - Tobs

    h = 0.5  # Bandwidth for Gaussian Kernel

    # Leave just the position information
    trajs = []
    for i in range(len(trajectories)):
        trajs.append(trajectories[i][:, 0:2])

    # Obtain observed and predicted trajlets
    Xm, Xp = obs_pred_trajectories(trajs, Tobs, Tpred + Tobs)

    # Estimate the entropy for every trajectory
    entropy_values = []
    for k in range(N_t):
        w = weights(Xm, k, h)
        entropy_values.append(entropy(Xp, k, h, w, M, replace=replace))
        if k % 20 == 0:
            print(k, 'out of', N_t)

    print('Done with the entropies of', dataset_name)
    return entropy_values


def entropies_set(opentraj_root, datasets_name, M=30, replace=False):
    entropies_dir = os.path.join(opentraj_root, 'entropies__temp')
    if not os.path.exists(entropies_dir): os.makedirs(entropies_dir)

    trajectories_set = get_trajlets(opentraj_root, datasets_name)

    entropy_values_set = {}
    maximum = []
    for name in trajectories_set:
        if replace == True:
            R = '-R'
        else:
            R = '-NR'
        trajlet_entropy_file = os.path.join(entropies_dir, name + str(M) + '-entropy' + R + '.npy')
        if os.path.exists(trajlet_entropy_file):
            entropy_values = np.load(trajlet_entropy_file)
            print("loading entropies from: ", trajlet_entropy_file)
        else:
            entropy_values = get_entropies(opentraj_root, trajectories_set[name], name, M, replace=replace)
            np.save(trajlet_entropy_file, entropy_values)
            print("writing entropies ndarray into: ", trajlet_entropy_file)
        entropy_values_set.update({name: entropy_values})
        # if name in reference_folders:
        #     path = os.path.join(opentraj_root, reference_folders[name])
            # visualize_max_entropy(trajectories_set[name], np.argmax(entropy_values_set[name]),path,name,replace)
    return entropy_values_set


# --------------------------------Main--------------------------------------------
def run(datasets, output_dir):
    datasets_name = all_dataset_names
    rep = True
    ntpys = entropies_set(args.root_path, datasets_name, 30, replace=rep)

    entropies = np.array([])
    labels = []
    maximum = []
    for dataset in ntpys:
        entropies = np.concatenate((entropies, ntpys[dataset]))
        max_index = np.argmax(ntpys[dataset])
        for i in range(len(ntpys[dataset])):
            labels.append(dataset)
            if i == max_index:
                maximum.append('Maximum entropy')
            else:
                maximum.append('Not maximum entropy')

    data = {'Entropy': entropies, 'Dataset': labels}
    data = pd.DataFrame(data, columns=['Entropy', 'Dataset'])

    # Obtain swarmplots

    sns.set(style="whitegrid")
    colors = ["windows blue", "amber", "greyish", "faded green", "dusty purple"]
    plt.figure(figsize=(12, 6))
    ax = sns.swarmplot(y='Entropy', x='Dataset', data=data, palette='bright')  # , hue = maximum)
    if rep == True:
        titl = 'Entropies with replacement'
        R = 'R'
    else:
        titl = 'Entropies without replacement'
        R = 'NR'
    img_title = graphics_dir + '/' + 'Entropies-' + R + '.pdf'
    plt.title(titl)
    plt.savefig(img_title, format='pdf')
    plt.clf()


if __name__ == '__main__':
    from toolkit.benchmarking.load_all_datasets import get_datasets, get_trajlets, all_dataset_names

    opentraj_root = sys.argv[1]
    output_dir = sys.argv[2]

    dataset_names = all_dataset_names
    datasets = get_datasets(opentraj_root, dataset_names)
    run(datasets, output_dir)
