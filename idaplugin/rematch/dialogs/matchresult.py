import idaapi
import idc

from .. idasix import QtGui, QtWidgets, QtCore

from . import base
from .. import network

from . import resultscript


class MatchTreeWidgetItem(QtWidgets.QTreeWidgetItem):
  def __init__(self, api_id, *args, **kwargs):
    super(MatchTreeWidgetItem, self).__init__(*args, **kwargs)
    self.api_id = api_id

  def __lt__(self, other):
    column = self.treeWidget().sortColumn()
    if self.childCount() == 0 and other.childCount() == 0:
      try:
        return float(self.text(column)) < float(other.text(column))
      except ValueError:
        return self.text(column) < other.text(column)
    elif self.childCount() == 0 and other.childCount() > 0:
      return True
    elif self.childCount() > 0 and other.childCount() == 0:
      return False
    else:
      my_biggest_child = self.biggest_child()
      other_biggest_child = other.biggest_child()
      return my_biggest_child < other_biggest_child

  def biggest_child(self):
    return max(self.child(i) for i in range(self.childCount()))


class SearchTreeWidget(QtWidgets.QTreeWidget):
  def __init__(self, search_box, match_column, *args, **kwargs):
    super(SearchTreeWidget, self).__init__(*args, **kwargs)
    self.search_box = search_box
    self.match_column = match_column
    self.search_box.textEdited.connect(self.search)
    self.search_box.returnPressed.connect(self.search)

  def keyPressEvent(self, event):
    if event.text():
      self.search_box.keyPressEvent(event)
    else:
      super(SearchTreeWidget, self).keyPressEvent(event)

  def search(self, _=None):
    del _

    text = self.search_box.text().lower()
    start = self.currentItem()
    it = QtWidgets.QTreeWidgetItemIterator(self.currentItem())
    it += 1
    while it.value() != start:
      if it.value() is None:
        it = QtWidgets.QTreeWidgetItemIterator(self.topLevelItem(0))
      if text in it.value().text(self.match_column).lower():
        self.setCurrentItem(it.value())
        self.scrollToItem(it.value())
        return
      it += 1


class MatchResultDialog(base.BaseDialog):
  MATCH_NAME_COLUMN = 0
  CHECKBOX_COLUMN = 0
  MATCH_SCORE_COLUMN = 1
  DOCUMENTATION_SCORE_COLUMN = 2
  MATCH_KEY_COLUMN = 3

  LOCAL_ELEMENT_COLOR = QtGui.QBrush(QtGui.QColor(0x42, 0x86, 0xF4))
  LOCAL_ELEMENT_TOOLTIP = "Local function"
  REMOTE_ELEMENT_TOOLTIP = "Remote function"

  def __init__(self, task_id, modal=False, *args, **kwargs):
    kwargs['modal'] = modal
    super(MatchResultDialog, self).__init__(*args, **kwargs)

    self.task_id = task_id
    self.locals = None
    self.remotes = None
    self.matches = None
    self.data_recevied_count = None

    self.script_code = None
    self.script_compile = None
    self.script_dialog = None

    # buttons
    self.btn_set = QtWidgets.QPushButton('&Select best')
    self.btn_clear = QtWidgets.QPushButton('&Clear')
    self.btn_script = QtWidgets.QPushButton('Fi&lter')
    self.btn_apply = QtWidgets.QPushButton('&Apply Matches')

    size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                        QtWidgets.QSizePolicy.Fixed)
    self.btn_set.setSizePolicy(size_policy)
    self.btn_clear.setSizePolicy(size_policy)
    self.btn_script.setSizePolicy(size_policy)
    self.btn_apply.setSizePolicy(size_policy)

    # buttons layout
    self.hlayoutButtons = QtWidgets.QHBoxLayout()
    self.hlayoutButtons.addWidget(self.btn_set)
    self.hlayoutButtons.addWidget(self.btn_clear)
    self.hlayoutButtons.addWidget(self.btn_script)
    self.hlayoutButtons.addWidget(self.btn_apply)

    self.btn_set.clicked.connect(self.set_checks)
    self.btn_clear.clicked.connect(self.clear_checks)
    self.btn_script.clicked.connect(self.show_script)
    self.btn_apply.clicked.connect(self.apply_matches)

    # matches tree
    self.search_box = QtWidgets.QLineEdit()
    self.tree = SearchTreeWidget(search_box=self.search_box,
                                 match_column=self.MATCH_NAME_COLUMN)

    # tree columns
    self.tree.setHeaderLabels(("Function", "Score", "Doc. Score", "Engine"))

    self.tree.header().setDefaultSectionSize(20)
    self.tree.resizeColumnToContents(self.MATCH_SCORE_COLUMN)
    self.tree.resizeColumnToContents(self.DOCUMENTATION_SCORE_COLUMN)
    self.tree.setColumnWidth(self.MATCH_NAME_COLUMN, 150)

    # other tree properties
    self.tree.setFrameShape(QtWidgets.QFrame.NoFrame)
    self.tree.setAlternatingRowColors(True)
    self.tree.setSortingEnabled(True)
    self.tree.sortItems(self.MATCH_SCORE_COLUMN, QtCore.Qt.DescendingOrder)

    # text browser (code highlighting & display)
    self.textBrowser = QtWidgets.QTextBrowser()
    self.textBrowser.zoomIn(2)

    # splitter for code highlighting and tree
    self.frame = QtWidgets.QFrame()
    self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
    self.frame_layout = QtWidgets.QVBoxLayout()
    self.frame_layout.addWidget(self.tree)
    self.frame_layout.addWidget(self.search_box)
    self.frame_layout.addLayout(self.hlayoutButtons)
    self.frame.setLayout(self.frame_layout)

    self.splitter = QtWidgets.QSplitter()
    self.splitter.setOrientation(QtCore.Qt.Horizontal)
    self.splitter.addWidget(self.frame)
    self.splitter.addWidget(self.textBrowser)

    # main layout
    self.base_layout.addWidget(self.splitter)

    # connect events to handle
    self.tree.itemChanged.connect(self.item_changed)
    self.tree.itemSelectionChanged.connect(self.item_selection_changed)
    self.tree.itemDoubleClicked.connect(self.item_double_clicked)

    self.refresh_tree()

  def refresh_tree(self):
    self.locals = {}
    self.remotes = {}
    self.matches = {}
    self.data_recevied_count = 0

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
    subset = set(new_locals) & set(self.locals)
    if subset:
        raise Exception("Duplicate local resources: {}".format(subset))
    self.locals.update(new_locals)

    self.handle_page(response)

  def handle_remotes(self, response):
    new_remotes = {obj['id']: obj for obj in response['results']}
    subset = set(new_remotes) & set(self.remotes)
    if subset:
        raise Exception("Duplicate remotes resources: {}".format(subset))
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
    if 'next' not in response or not response['next']:
      self.data_recevied_count += 1
      if self.data_recevied_count >= 3:
        self.infuse_matches()
        self.populate_tree()
        self.set_checks()

  def infuse_matches(self):
    for local_id, matches in self.matches.items():
      self.locals[local_id]['matches'] = matches

  def get_obj(self, obj_id):
    if obj_id in self.locals:
      return self.locals[obj_id]
    else:
      return self.remotes[obj_id]

  def item_selection_changed(self):
    if not self.tree.selectedItems():
      return

    item = self.tree.selectedItems()[0]
    parent = item.parent()
    if parent is None:
      return

    id1 = item.parent().api_id
    id2 = item.api_id

    network.delayed_query("GET", "display/compare/", json=False,
                          params={"id1": id1, "id2": id2},
                          callback=self.handle_display_change)

  def handle_display_change(self, response):
    self.textBrowser.setHtml(response)
    self.textBrowser.reload()

  def item_double_clicked(self, item, column):
    del column

    if item.parent() is None:
      idaapi.jumpto(self.get_obj(item.api_id)['offset'])
      item.setExpanded(not item.isExpanded())

  def item_changed(self, item, column):
    # (is checkbox column?)
    if not column == self.CHECKBOX_COLUMN:
      return

    parent = item.parent()
    if parent is None:
      return

    self.blockSignals(True)
    item_index = parent.indexOfChild(item)
    for i in range(parent.childCount()):
      if i != item_index:
        curr_child = parent.child(i)
        curr_child.setCheckState(self.CHECKBOX_COLUMN, QtCore.Qt.Unchecked)
    self.blockSignals(False)

  def show_script(self):
    self.script_dialog = resultscript.ResultScriptDialog()
    self.script_dialog.accepted.connect(self.update_script)
    self.script_dialog.show()

  def update_script(self):
    self.script_code = self.script_dialog.get_code()
    self.script_dialog = None

    self.script_compile = compile(self.script_code, '<input>', 'exec')

    self.tree.clear()
    self.populate_tree()

  def apply_matches(self):
    root = self.tree.invisibleRootItem()
    apply_pbar = QtWidgets.QProgressDialog("", "&Cancel", 0, root.childCount())
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        if remote_item.checkState(self.CHECKBOX_COLUMN):
          # TODO: apply metches
          # item_obj = self.documentation[remote_item.api_id]
          # remote_docs = item_obj["documentation"]
          # apply_documentation(local_item.ea, remote_docs)
          break
      apply_pbar.setValue(apply_pbar.value() + 1)

    # refresh ida's views
    # _idaapi.refresh_idaview_anyway()

  def clear_checks(self):
    root = self.tree.invisibleRootItem()
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        remote_item.setCheckState(self.CHECKBOX_COLUMN, QtCore.Qt.Unchecked)

  def set_checks(self):
    root = self.tree.invisibleRootItem()
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      checked = False
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        if remote_item.checkState(self.CHECKBOX_COLUMN):
          checked = True
          break

      if not checked and local_item.childCount():
        remote_item = local_item.child(local_item.childCount() - 1)
        remote_item.setCheckState(self.CHECKBOX_COLUMN, QtCore.Qt.Checked)

  def build_context(self, local, match=None, remote=None):
    context = {'Filter': False}

    local = {'offset': local['offset'], 'name': local['name'],
             'local': True}
    context['local'] = local

    if remote:
      remote = {'offset': remote['offset'], 'name': remote['name'],
                'score': match["score"], 'key': match["type"],
                'local': remote['id'] in self.locals.keys()}
    context['remote'] = remote

    return context

  def should_filter(self, context):
    if not self.script_compile:
      return False

    try:
      exec(self.script_compile, context)
    except Exception as ex:
      errors = context.get('Errors', 'stop')
      if errors == 'stop':
        self.script_compile = None
        idc.Warning("Filter function encountered a runtime error: {}.\n"
                    "Disabling filters.".format(ex))
      elif errors == 'filter':
        pass
      elif errors == 'hide':
        return True
      elif 'errors' == 'show':
        return False
    return 'Filter' in context and context['Filter']

  def populate_tree(self):
    self.tree.sortItems(self.DOCUMENTATION_SCORE_COLUMN,
                        QtCore.Qt.DescendingOrder)
    self.tree.setSortingEnabled(False)

    for local_obj in self.locals.values():
      context = self.build_context(local_obj)
      if self.should_filter(context):
        continue

      local_item = self.populate_item(self.tree, local_obj)
      for match_obj in local_obj['matches']:
        remote_obj = self.remotes[match_obj['remote_id']]

        context = self.build_context(local_obj, match_obj, remote_obj)
        if self.should_filter(context):
          continue

        self.populate_item(local_item, remote_obj, match_obj)
      self.tree.expandItem(local_item)

    # fake click on first child item so browser won't show a blank page
    root = self.tree.invisibleRootItem()
    if root.childCount():
      if root.child(0).childCount():
        item = root.child(0).child(0)
        item.setSelected(True)

  def populate_item(self, parent_item, item_obj, match_obj=None):
    item_id = item_obj['id']
    item_name = item_obj['name']

    tree_item = MatchTreeWidgetItem(item_id, parent_item)
    item_flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
    if match_obj:
      item_flags |= QtCore.Qt.ItemIsUserCheckable

    tree_item.setFlags(item_flags)
    tree_item.setText(self.MATCH_NAME_COLUMN, item_name)

    if item_id in self.locals:
      tree_item.setForeground(self.MATCH_NAME_COLUMN,
                                self.LOCAL_ELEMENT_COLOR)
      tree_item.setToolTip(self.MATCH_NAME_COLUMN,
                             self.LOCAL_ELEMENT_TOOLTIP)
    else:
      tree_item.setToolTip(self.MATCH_NAME_COLUMN,
                             self.REMOTE_ELEMENT_TOOLTIP)

    if match_obj:
      tree_item.setText(self.MATCH_SCORE_COLUMN,
                          str(round(match_obj['score'], 2)))
      tree_item.setText(self.DOCUMENTATION_SCORE_COLUMN,
                          str(round(0, 2)))
      tree_item.setText(self.MATCH_KEY_COLUMN,
                          str(match_obj['type']))
      tree_item.setCheckState(self.CHECKBOX_COLUMN, QtCore.Qt.Unchecked)

    return tree_item
