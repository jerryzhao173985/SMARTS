# MIT License
#
# Copyright (C) 2021. Huawei Technologies Co., Ltd. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import json
import os
import re
import sys

# Set environment to better support Ray
os.environ["MKL_NUM_THREADS"] = "1"
import argparse
import glob
import time
from pydoc import locate

import gym
import numpy as np
import psutil
import ray
import torch
import yaml

from smarts.zoo.registry import make
from ultra.utils.episode import LogInfo, episodes
from ultra.utils.ray import default_ray_kwargs

num_gpus = 1 if torch.cuda.is_available() else 0


def evaluation_check(
    agent,
    episode,
    agent_id,
    policy_class,
    eval_rate,
    eval_episodes,
    max_episode_steps,
    scenario_info,
    timestep_sec,
    headless,
    log_dir,
    evaluations,
):

    agent_itr = episode.get_itr(agent_id)

    print(
        f"Agent iteration : {agent_itr}, Eval rate : {eval_rate}, last_eval_iter : {episode.last_eval_iteration}"
    )
    if (agent_itr + 1) % eval_rate == 0 and episode.last_eval_iteration != agent_itr:
        checkpoint_dir = episode.checkpoint_dir(agent_itr)
        agent.save(checkpoint_dir)
        eval_handle = evaluate.remote(
            experiment_dir=episode.experiment_dir,
            agent_id=agent_id,
            policy_class=policy_class,
            seed=episode.eval_count,
            itr_count=agent_itr,
            checkpoint_dir=checkpoint_dir,
            scenario_info=scenario_info,
            num_episodes=eval_episodes,
            max_episode_steps=max_episode_steps,
            headless=headless,
            timestep_sec=timestep_sec,
            log_dir=log_dir,
        )
        evaluations[eval_handle] = (episode.active_tag, agent_id, episode)
        episode.last_eval_iteration = agent_itr
        episode.eval_count += 1


def collect_eval(evaluations: dict):
    ready, not_ready = ray.wait([k for k in evaluations.keys()], timeout=0)

    for r in ready:
        active_tag, e_agent_id, e = evaluations.pop(r)
        e.eval_mode()
        e.info[active_tag][e_agent_id] = ray.get(r)

        e.record_tensorboard()
        e.train_mode()
    return len(evaluations) < 1


# Number of GPUs should be split between remote functions.
@ray.remote(num_gpus=num_gpus / 2, max_calls=1)
def evaluate(
    experiment_dir,
    seed,
    agent_id,
    policy_class,
    itr_count,
    checkpoint_dir,
    scenario_info,
    num_episodes,
    max_episode_steps,
    headless,
    timestep_sec,
    log_dir,
):

    torch.set_num_threads(1)
    spec = make(
        locator=policy_class,
        checkpoint_dir=checkpoint_dir,
        experiment_dir=experiment_dir,
        max_episode_steps=max_episode_steps,
    )

    env = gym.make(
        "ultra.env:ultra-v0",
        agent_specs={agent_id: spec},
        scenario_info=scenario_info,
        headless=headless,
        timestep_sec=timestep_sec,
        seed=seed,
        eval_mode=True,
    )

    agent = spec.build_agent()
    summary_log = LogInfo()
    logs = []

    for episode in episodes(num_episodes, etag=policy_class, log_dir=log_dir):
        observations = env.reset()
        state = observations[agent_id]
        dones, infos = {"__all__": False}, None

        episode.reset(mode="Evaluation")
        while not dones["__all__"]:
            action = agent.act(state, explore=False)
            observations, rewards, dones, infos = env.step({agent_id: action})

            next_state = observations[agent_id]

            state = next_state

            episode.record_step(agent_id=agent_id, infos=infos, rewards=rewards)

        episode.record_episode()
        logs.append(episode.info[episode.active_tag][agent_id].data)

        for key, value in episode.info[episode.active_tag][agent_id].data.items():
            if not isinstance(value, (list, tuple, np.ndarray)):
                summary_log.data[key] += value

    for key, val in summary_log.data.items():
        if not isinstance(val, (list, tuple, np.ndarray)):
            summary_log.data[key] /= num_episodes

    env.close()

    return summary_log


if __name__ == "__main__":
    parser = argparse.ArgumentParser("intersection-single-agent-evaluation")
    parser.add_argument(
        "--task", help="Tasks available : [0, 1, 2]", type=str, default="1"
    )
    parser.add_argument(
        "--level",
        help="Levels available : [easy, medium, hard, no-traffic]",
        type=str,
        default="easy",
    )
    parser.add_argument("--models", default="models/", help="Directory to saved models")
    parser.add_argument(
        "--episodes", help="Number of training episodes", type=int, default=200
    )
    parser.add_argument(
        "--max-episode-steps",
        help="Maximum number of steps per episode",
        type=int,
        default=10000,
    )
    parser.add_argument(
        "--timestep", help="Environment timestep (sec)", type=float, default=0.1
    )
    parser.add_argument(
        "--headless", help="Run without envision", type=bool, default=False
    )
    parser.add_argument(
        "--experiment-dir",
        help="Path to spec file that includes adapters and policy parameters",
        type=str,
    )
    parser.add_argument(
        "--log-dir",
        help="Log directory location",
        default="logs",
        type=str,
    )
    args = parser.parse_args()

    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir)

    m = re.search(
        "ultra(.)*([a-zA-Z0-9_]*.)+([a-zA-Z0-9_])+:[a-zA-Z0-9_]+((-)*[a-zA-Z0-9_]*)*",
        args.models,
    )

    try:
        policy_class = m.group(0)
    except AttributeError as e:
        # default policy class
        policy_class = "ultra.baselines.sac:sac-v0"

    if not os.path.exists(args.models):
        raise "Path to model is invalid"

    if not os.listdir(args.models):
        raise "No models to evaluate"

    sorted_models = sorted(
        glob.glob(f"{args.models}/*"), key=lambda x: int(x.split("/")[-1])
    )
    base_dir = os.path.dirname(__file__)
    pool_path = os.path.join(base_dir, "agent_pool.json")

    ray.init()
    try:
        AGENT_ID = "AGENT_008"
        for episode in episodes(
            len(sorted_models),
            etag=policy_class,
            log_dir=args.log_dir,
        ):
            model = sorted_models[episode.index]
            print("model: ", model)
            episode_count = model.split("/")[-1]
            episode.eval_mode()
            episode.info[episode.active_tag][AGENT_ID] = ray.get(
                [
                    evaluate.remote(
                        experiment_dir=args.experiment_dir,
                        agent_id=AGENT_ID,
                        policy_class=policy_class,
                        seed=episode.eval_count,
                        itr_count=0,
                        checkpoint_dir=model,
                        scenario_info=(args.task, args.level),
                        num_episodes=int(args.episodes),
                        max_episode_steps=int(args.max_episode_steps),
                        timestep_sec=float(args.timestep),
                        headless=args.headless,
                        log_dir=args.log_dir,
                    )
                ]
            )[0]
            episode.record_tensorboard()
            episode.eval_count += 1
    finally:
        time.sleep(1)
        ray.shutdown()
