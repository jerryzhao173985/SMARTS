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
import os
from ultra.utils.ray import default_ray_kwargs

# Set environment to better support Ray
os.environ["MKL_NUM_THREADS"] = "1"
import time
import psutil, pickle, dill
import  ray, torch, argparse
from smarts.zoo.registry import make
from ultra.env.rllib_ultra_env import RLlibUltraEnv
num_gpus = 1 if torch.cuda.is_available() else 0


# @ray.remote(num_gpus=num_gpus / 2, max_calls=1)
@ray.remote(num_gpus=num_gpus / 2)
def train(task, num_episodes, policy_class, eval_info, timestep_sec, headless, seed):
    torch.set_num_threads(1)
    total_step = 0
    finished = False

    # --------------------------------------------------------
    # Initialize Agent and social_vehicle encoding method
    # -------------------------------------------------------
    AGENT_ID = "007"

    spec = make(locator=policy_class)
    # env = gym.make(
    #     "ultra.env:ultra-v0",
    #     agent_specs={AGENT_ID: spec},
    #     scenario_info=task,
    #     headless=headless,
    #     timestep_sec=timestep_sec,
    #     seed=seed,
    # )

    tune_config = {
        "env": RLlibUltraEnv,
        "log_level": "WARN",
        "num_workers": num_workers,
        "env_config": {
            "seed": tune.sample_from(lambda spec: random.randint(0, 300)),
            "scenarios": [str(Path(scenario).expanduser().resolve().absolute())],
            "headless": headless,
            "agent_specs": {
                f"AGENT-{i}": rllib_agent["agent_spec"] for i in range(num_agents)
            },
        },
        "multiagent": {"policies": rllib_policies},
        "callbacks": Callbacks,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser("intersection-single-agent")
    parser.add_argument(
        "--task", help="Tasks available : [0, 1, 2, 3]", type=str, default="1"
    )
    parser.add_argument(
        "--level",
        help="Tasks available : [easy, medium, hard, no-traffic]",
        type=str,
        default="easy",
    )
    parser.add_argument(
        "--episodes", help="number of training episodes", type=int, default=1000000
    )
    parser.add_argument(
        "--timestep", help="environment timestep (sec)", type=float, default=0.1
    )
    parser.add_argument(
        "--headless", help="run without envision", type=bool, default=False
    )
    parser.add_argument(
        "--eval-episodes", help="number of evaluation episodes", type=int, default=200
    )
    parser.add_argument(
        "--eval-rate",
        help="evaluation rate based on number of observations",
        type=int,
        default=10000,
    )

    parser.add_argument(
        "--seed", help="environment seed", default=2, type=int,
    )
    args = parser.parse_args()

    num_cpus = max(
        1, psutil.cpu_count(logical=False) - 1
    )  # remove `logical=False` to use all cpus

    policy_class = "ultra.baselines.sac:sac-v0"
    # ray_kwargs = default_ray_kwargs(num_cpus=num_cpus, num_gpus=num_gpus)
    ray.init()  # **ray_kwargs)
    # try:
    ray.wait(
        [
            train.remote(
                task=(args.task, args.level),
                num_episodes=int(args.episodes),
                eval_info={
                    "eval_rate": float(args.eval_rate),
                    "eval_episodes": int(args.eval_episodes),
                },
                timestep_sec=float(args.timestep),
                headless=args.headless,
                policy_class=policy_class,
                seed=args.seed,
            )
        ]
    )
    # finally:
    #     time.sleep(1)
    #     ray.shutdown()
