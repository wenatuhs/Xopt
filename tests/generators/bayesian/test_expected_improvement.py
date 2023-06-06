from copy import deepcopy

import pandas as pd
import pytest
import torch
from botorch.acquisition import ExpectedImprovement

from xopt.base import Xopt
from xopt.evaluator import Evaluator
from xopt.generators.bayesian.expected_improvement import ExpectedImprovementGenerator
from xopt.generators.bayesian.upper_confidence_bound import UCBOptions
from xopt.resources.testing import TEST_VOCS_BASE, TEST_VOCS_DATA, xtest_callable
from xopt.vocs import ObjectiveEnum, VOCS


class TestExpectedImprovement:
    def test_init(self):
        ei_gen = ExpectedImprovementGenerator(TEST_VOCS_BASE)
        ei_gen.options.dict()

        with pytest.raises(ValueError):
            ExpectedImprovementGenerator(TEST_VOCS_BASE, UCBOptions())

    def test_generate(self):
        gen = ExpectedImprovementGenerator(
            TEST_VOCS_BASE,
        )
        gen.options.optim.raw_samples = 1
        gen.options.optim.num_restarts = 1
        gen.options.acq.monte_carlo_samples = 1
        gen.data = TEST_VOCS_DATA

        candidate = gen.generate(1)
        assert len(candidate) == 1

        # candidate = gen.generate(2)
        # assert len(candidate) == 2

    def test_generate_w_overlapping_objectives_constraints(self):
        test_vocs = deepcopy(TEST_VOCS_BASE)
        test_vocs.constraints = {"y1": ["GREATER_THAN", 0.0]}
        gen = ExpectedImprovementGenerator(
            test_vocs,
        )
        gen.options.optim.raw_samples = 1
        gen.options.optim.num_restarts = 1
        gen.options.acq.monte_carlo_samples = 1
        gen.data = TEST_VOCS_DATA

        candidate = gen.generate(1)
        assert len(candidate) == 1

    def test_in_xopt(self):
        evaluator = Evaluator(function=xtest_callable)
        ucb_gen = ExpectedImprovementGenerator(
            TEST_VOCS_BASE,
        )
        ucb_gen.options.optim.raw_samples = 1
        ucb_gen.options.optim.num_restarts = 1

        xopt = Xopt(generator=ucb_gen, evaluator=evaluator, vocs=TEST_VOCS_BASE)

        # initialize with single initial candidate
        xopt.step()

        # now use bayes opt
        for _ in range(1):
            xopt.step()

    def test_in_xopt_w_proximal(self):
        evaluator = Evaluator(function=xtest_callable)
        ucb_gen = ExpectedImprovementGenerator(
            TEST_VOCS_BASE,
        )
        ucb_gen.options.optim.raw_samples = 1
        ucb_gen.options.optim.num_restarts = 1
        ucb_gen.options.acq.proximal_lengthscales = [1.0, 1.0]

        xopt = Xopt(generator=ucb_gen, evaluator=evaluator, vocs=TEST_VOCS_BASE)

        # initialize with single initial candidate
        xopt.step()

        # now use bayes opt
        for _ in range(1):
            xopt.step()

    def test_acquisition_accuracy(self):
        train_x = torch.tensor([0.01, 0.3, 0.6, 0.99]).double()
        train_y = torch.sin(2 * torch.pi * train_x)
        train_data = pd.DataFrame({"x1": train_x.numpy(), "y1": train_y.numpy()})
        test_x = torch.linspace(0.0, 1.0, 1000)

        for objective in ObjectiveEnum:
            vocs = VOCS(
                **{"variables": {"x1": [0.0, 1.0]}, "objectives": {"y1": objective}}
            )
            generator = ExpectedImprovementGenerator(vocs)
            generator.add_data(train_data)
            model = generator.train_model().models[0]

            # xopt acquisition function
            acq = generator.get_acquisition(model)

            # analytical acquisition function
            if objective == "MAXIMIZE":
                an_acq = ExpectedImprovement(model, best_f=train_y.max(), maximize=True)
            else:
                an_acq = ExpectedImprovement(
                    model, best_f=train_y.min(), maximize=False
                )

            # compare candidates (maximum in test data)
            with torch.no_grad():
                acq_v = acq(test_x.reshape(-1, 1, 1))
                candidate = test_x[torch.argmax(acq_v)]
                an_acq_v = an_acq(test_x.reshape(-1, 1, 1))
                an_candidate = test_x[torch.argmax(an_acq_v)]

            # difference should be small
            assert torch.abs(an_candidate - candidate) < 0.01
