# Copyright 2026 Stafl Systems
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
"""Unit tests for the station server's POST /tests/<uid>/abort endpoint."""

from unittest import mock

from openhtf.core import test_state
from openhtf.output.servers import station_server
import tornado.testing
import tornado.web

_UID = '123:abc:def:456'
_URL = '/tests/%s/abort' % _UID
_JSON = {'Content-Type': 'application/json'}


class AbortHandlerTest(tornado.testing.AsyncHTTPTestCase):

  def get_app(self):
    return tornado.web.Application([
        (r'/tests/(?P<test_uid>[\w\d:]+)/abort', station_server.AbortHandler),
    ])

  def setUp(self):
    super().setUp()
    self.test = mock.Mock(uid=_UID)
    self.test.abort.return_value = True
    self.state = mock.Mock(status=test_state.TestState.Status.RUNNING)
    self.state.Status = test_state.TestState.Status
    patcher = mock.patch.object(
        station_server, '_get_executing_test',
        side_effect=lambda: (self.test, self.state))
    patcher.start()
    self.addCleanup(patcher.stop)

  def _post(self, headers=None):
    return self.fetch(
        _URL, method='POST', body='{}', headers=headers or dict(_JSON))

  def test_stops_the_running_test(self):
    response = self._post()

    self.assertEqual(204, response.code)
    self.test.abort.assert_called_once_with()

  def test_same_origin_request_is_accepted(self):
    origin = 'http://127.0.0.1:%d' % self.get_http_port()

    response = self._post({**_JSON, 'Origin': origin})

    self.assertEqual(204, response.code)

  def test_request_from_another_page_is_refused(self):
    response = self._post({**_JSON, 'Origin': 'http://evil.example'})

    self.assertEqual(403, response.code)
    self.test.abort.assert_not_called()

  def test_form_post_is_refused(self):
    """A form-like body is what a browser sends cross-origin unasked."""
    response = self._post({'Content-Type': 'text/plain'})

    self.assertEqual(403, response.code)
    self.test.abort.assert_not_called()

  def test_no_cors_headers_and_no_preflight(self):
    response = self.fetch(_URL, method='OPTIONS')

    self.assertNotEqual(204, response.code)
    self.assertNotIn('Access-Control-Allow-Origin', response.headers)

  def test_unknown_test_uid(self):
    self.test.uid = 'other:uid:x:1'

    self.assertEqual(404, self._post().code)
    self.test.abort.assert_not_called()

  def test_no_test_running(self):
    self.test, self.state = None, None

    self.assertEqual(404, self._post().code)

  def test_test_not_started_yet(self):
    self.state.status = test_state.TestState.Status.WAITING_FOR_TEST_START

    self.assertEqual(409, self._post().code)
    self.test.abort.assert_not_called()

  def test_already_stopping(self):
    self.test.abort.return_value = False

    self.assertEqual(409, self._post().code)
