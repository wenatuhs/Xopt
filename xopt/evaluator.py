import logging
from concurrent.futures import Executor, Future, ProcessPoolExecutor, ThreadPoolExecutor
from enum import Enum
from threading import Lock
from types import FunctionType
from typing import Callable, Dict

import pandas as pd

from xopt.pydantic import XoptBaseModel
from xopt.utils import get_function, get_function_defaults

logger = logging.getLogger(__name__)


class ExecutorEnum(str, Enum):
    thread_pool_executor = "ThreadPoolExecutor"
    process_pool_executor = "ProcessPoolExecutor"
    normal_executor = "NormalExecutor"


class EvaluatorOptions(XoptBaseModel):
    """
    Evaluator model.
    """

    function: Callable[..., dict]
    function_kwargs: dict = {}
    max_workers: int = 1
    executor: ExecutorEnum = ExecutorEnum.normal_executor

    class Config:
        extra = "forbid"
        use_enum_values = True
        json_encoders = {FunctionType: lambda x: x.__module__ + "." + x.__name__}


class Evaluator:
    def __init__(
        self,
        function: Callable,
        max_workers: int = 1,
        executor: str = "NormalExecutor",
        function_kwargs: dict = {},
    ):
        """
        wrapper around the executor class, by default it uses a dummy
        executor with max_workers=1

        """

        # Fill defaults
        kw = get_function_defaults(function)
        kw.update(function_kwargs)

        self.options = EvaluatorOptions(
            function=function,
            max_workers=max_workers,
            executor=executor,
            function_kwargs=kw,
        )
        if self.options.executor == ExecutorEnum.normal_executor:
            logger.debug("using normal executor")
            self._executor = DummyExecutor()
            self.max_workers = 1
        elif self.options.executor == ExecutorEnum.thread_pool_executor:
            logger.debug(
                f"using thread pool executor with max_workers={self.options.max_workers}"
            )
            self._executor = ThreadPoolExecutor(max_workers=self.options.max_workers)
            self.max_workers = self.options.max_workers
        elif self.options.executor == ExecutorEnum.process_pool_executor:
            logger.debug(
                f"using process pool executor with max_workers={self.options.max_workers}"
            )
            self._executor = ProcessPoolExecutor(max_workers=self.options.max_workers)
        self.function = self.options.function

    @classmethod
    def from_options(cls, options: EvaluatorOptions):
        return cls(**options.dict())

    def evaluate(self, input: Dict, **kwargs):
        """
        Evaluate a single input dict using Evaluator.function with
        Evaluator.function_kwargs.

        Further kwargs are passed to the function.

        Inputs:
            inputs: dict of inputs to be evaluated
            **kwargs: additional kwargs to pass to the function

        Returns:
            function(input, **function_kwargs_updated)

        """
        return self.function(input, **{**self.options.function_kwargs, **kwargs})

    def submit(self, input: Dict):
        """submit a single input to the executor"""
        if not isinstance(input, dict):
            raise ValueError("input must be a dictionary")
        return self._executor.submit(
            self.function, input, **self.options.function_kwargs
        )

    def submit_data(self, input_data: pd.DataFrame):
        """submit dataframe of inputs to executor"""
        input_data = pd.DataFrame(input_data)  # cast to dataframe
        futures = {}
        for index, row in input_data.iterrows():
            future = self.submit(dict(row))
            futures[index] = future

        return futures


class DummyExecutor(Executor):
    """
    Dummy executor.

    From: https://stackoverflow.com/questions/10434593/dummyexecutor-for-pythons-futures

    """

    def __init__(self):
        self._shutdown = False
        self._shutdownLock = Lock()

    def submit(self, fn, *args, **kwargs):
        with self._shutdownLock:
            if self._shutdown:
                raise RuntimeError("cannot schedule new futures after shutdown")

            f = Future()
            try:
                result = fn(*args, **kwargs)
            except BaseException as e:
                f.set_exception(e)
            else:
                f.set_result(result)

            return f

    def shutdown(self, wait=True):
        with self._shutdownLock:
            self._shutdown = True
