# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for test_descriptor module."""

import re
import threading
import time
import unittest
from unittest import mock

import openhtf
from openhtf.core import test_descriptor
from openhtf.core import test_record


class RegexMatcher(object):

  def __init__(self, pattern):
    self.pattern = pattern

  def __eq__(self, other):
    return re.search(self.pattern, other) is not None


class TestTest(unittest.TestCase):

  @mock.patch.object(test_descriptor, '_LOG')
  def test_output_cb_error_stacktrace_log(self, mock_log):

    def phase():
      return

    def callback(test_record):
      del test_record
      raise Exception('test123')

    test = test_descriptor.Test(phase)
    test.add_output_callbacks(callback)
    test.execute()
    mock_log.error.assert_called_once_with(
        mock.ANY, callback, RegexMatcher(r'test_descriptor_test(.|\n)*test123'))


class AbortTest(unittest.TestCase):
  """Test.abort(): an operator stop, e.g. from the station web UI."""

  def _start(self, phase, teardown):
    test = openhtf.Test(
        openhtf.PhaseGroup(main=[phase], teardown=[teardown]))
    records = []
    test.add_output_callbacks(records.append)
    thread = threading.Thread(
        target=test.execute, kwargs={'test_start': lambda: 'dut'})
    thread.start()
    return test, thread, records

  def test_abort_ends_aborted_and_still_runs_teardown(self):
    started = threading.Event()
    teardown_ran = threading.Event()

    def busy_phase(test):
      del test  # Unused.
      started.set()
      for _ in range(200):  # Short sleeps, so the phase thread can be killed.
        time.sleep(0.05)

    def teardown(test):
      del test  # Unused.
      teardown_ran.set()

    test, thread, records = self._start(busy_phase, teardown)
    self.assertTrue(started.wait(5))

    self.assertTrue(test.abort())
    thread.join(10)

    self.assertFalse(thread.is_alive())
    self.assertTrue(teardown_ran.is_set())
    self.assertEqual(test_record.Outcome.ABORTED, records[0].outcome)

  def test_second_abort_does_nothing_and_teardown_still_runs(self):
    """A double-clicked stop button must not force-stop the process the way a
    second SIGINT does, which would skip teardown."""
    started = threading.Event()
    in_teardown = threading.Event()
    finish_teardown = threading.Event()
    teardown_finished = threading.Event()

    def busy_phase(test):
      del test  # Unused.
      started.set()
      for _ in range(200):
        time.sleep(0.05)

    def slow_teardown(test):
      del test  # Unused.
      in_teardown.set()
      finish_teardown.wait(5)
      teardown_finished.set()

    test, thread, records = self._start(busy_phase, slow_teardown)
    self.assertTrue(started.wait(5))
    self.assertTrue(test.abort())
    self.assertTrue(in_teardown.wait(5))

    self.assertFalse(test.abort())
    finish_teardown.set()
    thread.join(10)

    self.assertTrue(teardown_finished.is_set())
    self.assertEqual(test_record.Outcome.ABORTED, records[0].outcome)

  def test_abort_without_a_running_test_does_nothing(self):
    test = openhtf.Test(openhtf.PhaseGroup(main=[lambda: None]))

    self.assertFalse(test.abort())
