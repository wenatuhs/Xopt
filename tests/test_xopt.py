import math
from abc import ABC
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from xopt.asynchronous import AsynchronousXopt
from xopt.base import Xopt
from xopt.errors import XoptError
from xopt.evaluator import Evaluator
from xopt.generator import Generator
from xopt.generators.random import RandomGenerator
from xopt.resources.testing import TEST_VOCS_BASE, xtest_callable
from xopt.vocs import VOCS


class DummyGenerator(Generator, ABC):
    name = "dummy"

    def add_data(self, new_data: pd.DataFrame):
        self.data = pd.concat([self.data, new_data], axis=0)

    def generate(self, n_candidates) -> pd.DataFrame:
        pass

    def default_options(self):
        pass


class TestXopt:
    def test_init(self):
        # init with generator and evaluator
        def dummy(x):
            pass

        evaluator = Evaluator(function=dummy)
        gen = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        Xopt(generator=gen, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE))

        # init with yaml
        YAML = """
        evaluator:
            function: xopt.resources.test_functions.tnk.evaluate_TNK
            function_kwargs:
                a: 999

        generator:
            name: random

        vocs:
            variables:
                x1: [0, 3.14159]
                x2: [0, 3.14159]
            objectives: {y1: MINIMIZE, y2: MINIMIZE}
            constraints:
                c1: [GREATER_THAN, 0]
                c2: [LESS_THAN, 0.5]
            constants: {a: dummy_constant}

        """
        X = Xopt.from_yaml(YAML)
        assert X.vocs.variables == {"x1": [0, 3.14159], "x2": [0, 3.14159]}

    def test_evaluate_data(self):
        evaluator = Evaluator(function=xtest_callable)
        generator = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))

        xopt = Xopt(
            generator=generator, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE)
        )

        # test evaluating data w/o constants specified
        test_data = deepcopy(TEST_VOCS_BASE).random_inputs(3)

        # test list of dicts
        xopt.evaluate_data(test_data)

        # pandas
        xopt.evaluate_data(pd.DataFrame(test_data))

        # test dict of lists
        xopt.evaluate_data(pd.DataFrame(test_data).to_dict())

        # test single input
        xopt.evaluate_data({"x1": 0.5, "x2": 0.1})

    def test_function_checking(self):
        def f(x, a=True):
            if a:
                return {"f": x["x1"] ** 2 + x["x2"] ** 2}
            else:
                return {"f": False}

        def g(x, a=True):
            return False

        vocs = VOCS(
            variables={"x": [0, 2 * math.pi]},
            objectives={"f": "MINIMIZE"},
        )

        # init with generator and evaluator
        evaluator = Evaluator(function=f)
        generator = RandomGenerator(vocs=vocs)
        X = Xopt(
            generator=generator,
            evaluator=evaluator,
            vocs=vocs,
            strict=True,
        )
        with pytest.raises(XoptError):
            X.step()

        # init with generator and evaluator
        evaluator = Evaluator(function=g)  # Has non-dict return type
        generator = RandomGenerator(vocs=vocs)
        X2 = Xopt(
            generator=generator,
            evaluator=evaluator,
            vocs=vocs,
            strict=True,
        )
        with pytest.raises(XoptError):
            X2.step()

    def test_submit_bad_data(self):
        generator = DummyGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        evaluator = Evaluator(function=xtest_callable)
        X = Xopt(
            generator=generator,
            evaluator=evaluator,
            vocs=deepcopy(TEST_VOCS_BASE),
        )
        with pytest.raises(ValueError):
            X.evaluate_data(pd.DataFrame({"x1": [0.0, 5.0], "x2": [-3.0, 1.0]}))

    def test_add_data(self):
        generator = DummyGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        evaluator = Evaluator(function=xtest_callable)
        X = Xopt(
            generator=generator,
            evaluator=evaluator,
            vocs=deepcopy(TEST_VOCS_BASE),
        )
        assert X.generator.data is None
        X.add_data(pd.DataFrame({"x1": [0.0, 1.0], "x2": [0.0, 1.0]}))

        assert (
            len(X.generator.data) == 2
        ), f"len(X.generator.data) = {len(X.generator.data)}"

    def test_asynch(self):
        evaluator = Evaluator(function=xtest_callable)
        generator = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        X = AsynchronousXopt(
            generator=generator,
            evaluator=evaluator,
            vocs=deepcopy(TEST_VOCS_BASE),
        )
        n_steps = 5
        for i in range(n_steps):
            X.step()
        assert len(X.data) == n_steps

        # now use a threadpool evaluator with different number of max workers
        for mw in [2]:
            evaluator = Evaluator(
                function=xtest_callable, executor=ProcessPoolExecutor(), max_workers=mw
            )
            X2 = AsynchronousXopt(
                generator=generator,
                evaluator=evaluator,
                vocs=deepcopy(TEST_VOCS_BASE),
            )

            n_steps = 5
            for i in range(n_steps):
                X2.step()

            # TODO: better async test. This is unpredictable:
            # assert len(X2.data) == n_steps

    def test_strict(self):
        def bad_function(inval):
            raise ValueError

        evaluator = Evaluator(function=bad_function)
        gen = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        X = Xopt(generator=gen, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE))

        # should raise an error (default)
        with pytest.raises(XoptError):
            X.step()

        X2 = Xopt(generator=gen, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE))
        X2.strict = False

        X2.random_evaluate(10)
        # should run fine
        X2.step()
        assert "xopt_error_str" in X2.data.columns

    def test_process_futures(self):
        ss = 0

        def bad_function_sometimes(inval):
            if ss:
                raise ValueError
            else:
                return {"y1": 0.0, "c1": 0.0}

        evaluator = Evaluator(function=bad_function_sometimes)
        gen = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))
        X = AsynchronousXopt(
            generator=gen, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE)
        )
        X.strict = False

        # Submit to the evaluator some new inputs
        X.submit_data(deepcopy(TEST_VOCS_BASE).random_inputs(4))
        X.process_futures()

        ss = 1
        X.submit_data(deepcopy(TEST_VOCS_BASE).random_inputs(4))
        X.process_futures()

    def test_checkpointing(self):
        evaluator = Evaluator(function=xtest_callable)
        generator = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))

        X = Xopt(
            generator=generator, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE)
        )
        X.dump_file = "test_checkpointing.yaml"

        X.step()

        for _ in range(5):
            X.step()

        try:
            # try to load the state from nothing
            X2 = Xopt.from_file(X.dump_file)

            for _ in range(5):
                X2.step()

            assert isinstance(X2.generator, RandomGenerator)
            assert isinstance(X2.evaluator, Evaluator)
            assert X.vocs == X2.vocs

            assert len(X2.data) == 11

        except Exception as e:
            raise e
        finally:
            # clean up
            import os

            os.remove(X.dump_file)

    def test_random_evaluate(self):
        evaluator = Evaluator(function=xtest_callable)
        generator = RandomGenerator(vocs=deepcopy(TEST_VOCS_BASE))

        xopt = Xopt(
            generator=generator, evaluator=evaluator, vocs=deepcopy(TEST_VOCS_BASE)
        )

        # fixed seed for deterministic results
        xopt.random_evaluate(2, seed=1)
        xopt.random_evaluate(1)
        assert np.isclose(xopt.data["x1"].iloc[0], 0.488178)
        assert len(xopt.data) == 3
