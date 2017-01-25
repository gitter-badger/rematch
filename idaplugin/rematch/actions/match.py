from ..idasix import QtCore, QtWidgets
import idautils

from ..dialogs.match import MatchDialog
from ..dialogs.matchresult import MatchResultDialog

from .. import instances
from .. import network, netnode, logger
from . import base

import hashlib


class MatchAction(base.BoundFileAction):
  name = "&Match"
  dialog = MatchDialog

  def __init__(self, *args, **kwargs):
    super(MatchAction, self).__init__(*args, **kwargs)
    self.functions = None
    self.pbar = None
    self.timer = None
    self.results = None
    self.task_id = None
    self.file_version_id = None
    self.instance_set = []

    self.source = None
    self.source_single = None
    self.source_range = None
    self.target = None
    self.target_project = None
    self.target_file = None
    self.methods = None

    # results request state
    self.locals = {}
    self.remotes = {}
    self.matches = {}
    self.data_recevied_count = 0

  @staticmethod
  def calc_file_version_hash():
    version_obj = {}
    version_obj['functions'] = {offset: list(idautils.Chunks(offset))
                                  for offset in idautils.Functions()}
    version_str = repr(version_obj)
    version_hash = hashlib.md5(version_str).hexdigest()

    logger('match_action').info("file version string: %s", version_str)
    logger('match_action').info("file version hash: %s", version_hash)
    return version_hash

  def submit_handler(self, source, source_single, source_range, target,
                     target_project, target_file, methods):
    self.source = source
    self.source_single = source_single
    self.source_range = source_range
    self.target = target
    self.target_project = target_project if target == 'project' else None
    self.target_file = target_file if target == 'file' else None
    self.methods = methods

    file_version_hash = self.calc_file_version_hash()
    uri = "collab/files/{}/file_version/{}/".format(netnode.bound_file_id,
                                                    file_version_hash)
    return network.QueryWorker("POST", uri, json=True)

  def response_handler(self, file_version):
    self.file_version_id = file_version['id']

    if file_version['newly_created']:
      self.start_upload()
    else:
      self.start_task()

    return True

  def start_upload(self):
    self.functions = set(idautils.Functions())

    self.pbar = QtWidgets.QProgressDialog()
    self.pbar.setLabelText("Processing IDB... You may continue working,\nbut "
                           "please avoid making any ground-breaking changes.")
    self.pbar.setRange(0, len(self.functions))
    self.pbar.setValue(0)
    self.pbar.canceled.connect(self.cancel_upload)
    self.pbar.rejected.connect(self.reject_upload)
    self.pbar.accepted.connect(self.accept_upload)

    self.timer = QtCore.QTimer()
    self.timer.timeout.connect(self.perform_upload)
    self.timer.start(0)

    return True

  def perform_upload(self):
    try:
      offset = self.functions.pop()
    except KeyError:
      self.timer.stop()
      return

    try:
      func = instances.FunctionInstance(self.file_version_id, offset)
      self.instance_set.append(func.serialize())

      if len(self.instance_set) >= 100:
        network.delayed_query("POST", "collab/instances/",
                              params=self.instance_set, json=True,
                              callback=self.progress_advance)
        self.instance_set = []
        self.pbar.setMaximum(self.pbar.maximum() + 1)
      self.progress_advance()
    except Exception:
      self.cancel_upload()
      raise

  def progress_advance(self, result=None):
    del result
    new_value = self.pbar.value() + 1
    self.pbar.setValue(new_value)
    if new_value >= self.pbar.maximum():
      self.pbar.accept()

  def cancel_upload(self):
    self.timer.stop()
    self.timer = None
    self.pbar = None

  def reject_upload(self):
    self.cancel_upload()

  def accept_upload(self):
    self.timer.stop()
    self.timer = None
    self.pbar = None

    self.start_task()

  def start_task(self):
    if self.source == 'idb':
      self.source_range = [None, None]
    elif self.source == 'single':
      self.source_range = [self.source_single, self.source_single]
    elif self.source == 'range':
      pass
    else:
      raise NotImplementedError("Unsupported source type encountered in task "
                                "creation")

    params = {'source_file': netnode.bound_file_id,
              'source_file_version': self.file_version_id,
              'source_start': self.source_range[0],
              'source_end': self.source_range[1],
              'target_project': self.target_project,
              'target_file': self.target_file,
              'source': self.source, 'methods': self.methods}
    r = network.query("POST", "collab/tasks/", params=params, json=True)
    self.task_id = r['id']

    self.pbar = QtWidgets.QProgressDialog()
    self.pbar.setLabelText("Waiting for remote matching... You may continue "
                           "working without any limitations.")
    self.pbar.setRange(0, int(r['progress_max']) if r['progress_max'] else 0)
    self.pbar.setValue(int(r['progress']))
    self.pbar.canceled.connect(self.cancel_task)
    self.pbar.rejected.connect(self.reject_task)
    self.pbar.accepted.connect(self.accept_task)
    self.pbar.show()

    self.timer = QtCore.QTimer()
    self.timer.timeout.connect(self.perform_task)
    self.timer.start(1000)

  def perform_task(self):
    try:
      r = network.query("GET", "collab/tasks/{}/".format(self.task_id),
                        json=True)

      progress_max = int(r['progress_max']) if r['progress_max'] else None
      progress = int(r['progress'])
      status = r['status']
      if status == 'failed':
        self.pbar.reject()
      elif progress_max:
        self.pbar.setMaximum(progress_max)
        if progress >= progress_max:
          self.pbar.accept()
        else:
          self.pbar.setValue(progress)
    except Exception:
      self.cancel_task()
      raise

  def cancel_task(self):
    self.timer.stop()
    self.timer = None
    self.pbar = None

  def reject_task(self):
    self.cancel_task()

  def accept_task(self):
    self.timer.stop()
    self.timer = None
    self.pbar = None

    self.start_results()

  def start_results(self):
    self.pbar = QtWidgets.QProgressDialog()
    self.pbar.setLabelText("Receiving match results...")
    self.pbar.setRange(0, 0)
    self.pbar.setValue(0)
    self.pbar.canceled.connect(self.cancel_results)
    self.pbar.rejected.connect(self.reject_results)
    self.pbar.accepted.connect(self.accept_results)
    self.pbar.show()

    locals_url = "collab/tasks/{}/locals/".format(self.task_id)
    network.delayed_query("GET", locals_url, json=True, paginate=True,
                          params={'limit': 100}, callback=self.handle_locals)

    remotes_url = "collab/tasks/{}/remotes/".format(self.task_id)
    network.delayed_query("GET", remotes_url, json=True, paginate=True,
                          params={'limit': 100}, callback=self.handle_remotes)

    matches_url = "collab/tasks/{}/matches/".format(self.task_id)
    network.delayed_query("GET", matches_url, json=True, paginate=True,
                          params={'limit': 100}, callback=self.handle_matches)

  def handle_locals(self, response):
    new_locals = {obj['id']: obj for obj in response['results']}
    self.locals.update(new_locals)

    self.handle_page(response)

  def handle_remotes(self, response):
    new_remotes = {obj['id']: obj for obj in response['results']}
    self.remotes.update(new_remotes)

    self.handle_page(response)

  def handle_matches(self, response):
    def rename(o):
      o['local_id'] = o.pop('from_instance')
      o['remote_id'] = o.pop('to_instance')
      return o

    for obj in response['results']:
      obj = rename(obj)
      if obj['local_id'] in self.matches:
        self.matches[obj['local_id']].append(obj)
      else:
        self.matches[obj['local_id']] = [obj]

    self.handle_page(response)

  def handle_page(self, response):
    if 'previous' not in response or not response['previous']:
      self.pbar.setMaximum(self.pbar.maximum() + response['count'])

    self.pbar.setValue(max(self.pbar.value(), 0) + len(response['results']))

    if 'next' not in response or not response['next']:
      self.data_recevied_count += 1
      if self.data_recevied_count >= 3:
        self.accept_results()

  def cancel_results(self):
    self.pbar = None
    # XXX: todo properly cancel, including stopping paged fetches

  def reject_results(self):
    self.cancel_results()

  def accept_results(self):
    self.results = MatchResultDialog(self.task_id, self.locals, self.matches,
                                     self.remotes)
    self.results.show()
