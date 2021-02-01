import unittest, ray, os, ijson, sys
import shutil
from smarts.core.agent import AgentSpec
from smarts.zoo.registry import make
from ultra.train import train
from ultra.baselines.sac.sac.policy import SACPolicy

AGENT_ID = "001"
seed = 2

class TrainTest(unittest.TestCase):
    def test_train_cli(self):
        try:
            os.system(
                "python ultra/train.py --task 00 --level easy --episodes 1 --log-dir ultra/tests/logs"
            )
        except Exception as err:
            print(err)
            self.assertTrue(False)

    def test_locate_log_directory(self):
        log_dir = "ultra/tests/logs"
        try:
            os.system(
                f"python ultra/train.py --task 00 --level easy --policy ppo --episodes 1 --log-dir {log_dir}"
            )
        except Exception as err:
            print(err)
        
        if os.path.exists(log_dir):
            self.assertTrue(True)

    def test_train_single_agent(self):
        seed = 2
        policy_class = "ultra.baselines.sac:sac-v0"
        
        ray.init(ignore_reinit_error=True)
        try:
            ray.get(
                train.remote(
                    task=("00", "easy"),
                    policy_class=policy_class,
                    num_episodes=1,
                    eval_info={
                        "eval_rate": 1000,
                        "eval_episodes": 2,
                    },
                    timestep_sec=0.1,
                    headless=True,
                    seed=2,
                    log_dir="ultra/tests/logs"
                )
            )
            self.assertTrue(True)
            ray.shutdown()
        except ray.exceptions.WorkerCrashedError as err:
            print(err)
            self.assertTrue(False)
            ray.shutdown()
    
    def test_train_all_agents(self):
        seed = 2
        
        with open("ultra/agent_pool.json", 'r') as f:
            objects = ijson.items(f, 'agents')
            for o in objects:
                policy_pool = o
                for policy in policy_pool:
                    policy_path = policy_pool[policy]["path"]
                    policy_locator = policy_pool[policy]["locator"]
                    policy_class = str(policy_path) + ':' + str(policy_locator)
                    print(policy_class)
                    ray.init(ignore_reinit_error=True)
                    try:
                        ray.get(
                            train.remote(
                                task=("00", "easy"),
                                policy_class=policy_class,
                                num_episodes=1,
                                eval_info={
                                    "eval_rate": 1000,
                                    "eval_episodes": 2,
                                },
                                timestep_sec=0.1,
                                headless=True,
                                seed=2,
                                log_dir="ultra/tests/logs"
                            )
                        )
                        self.assertTrue(True)
                        ray.shutdown()
                    except ImportError as err:
                        print(err)
                        self.assertTrue(False)
                        ray.shutdown()
                    except ray.exceptions.WorkerCrashedError as err:
                        print(err)
                        self.assertTrue(False)
                        ray.shutdown()
    
    def test_spec_is_instance_agentspec(self):
        policy_class = "ultra.baselines.sac:sac-v0"
        spec = make(locator=policy_class)
        self.assertIsInstance(spec, AgentSpec)

    def test_agent_is_instance_policy(self):
        policy_class = "ultra.baselines.sac:sac-v0"
        spec = make(locator=policy_class)
        agent = spec.build_agent()
        self.assertIsInstance(agent, SACPolicy)

    def tearDown(self):
        if os.path.exists("ultra/tests/logs"):
            shutil.rmtree("ultra/tests/logs")

        os.system("pkill -9 ray")
    