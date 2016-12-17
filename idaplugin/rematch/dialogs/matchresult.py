import idaapi
import idc

from .. idasix import QtGui, QtWidgets, QtCore

from . import base
from .. import network
from .. import exceptions

from . import resultscript


def name_obj(obj):
  return obj["name"] if 'name' in obj else "sub_{0:X}".format(obj['offset'])


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

  def __init__(self, task_id, *args, **kwargs):
    super(MatchResultDialog, self).__init__(*args, **kwargs)

    self.task_id = task_id

    matches_url = "collab/tasks/{}/matches/".format(self.task_id)
    response = network.query("GET", matches_url, json=True)
    self.locals = {obj['id']: obj for obj in response['local']}
    self.remotes = response['remote']

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
    self.frame.sizeHint = lambda: QtCore.QSize(-1, -1)
    self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
    self.vlayoutMainFrame = QtWidgets.QVBoxLayout()
    self.vlayoutMainFrame.addWidget(self.tree)
    self.vlayoutMainFrame.addWidget(self.search_box)
    self.vlayoutMainFrame.addLayout(self.hlayoutButtons)
    self.frame.setLayout(self.vlayoutMainFrame)

    self.splitter = QtWidgets.QSplitter()
    self.splitter.setOrientation(QtCore.Qt.Horizontal)
    self.splitter.addWidget(self.frame)
    self.splitter.addWidget(self.textBrowser)
    self.splitter.setSizes([150, 650])

    # main layout
    self.base_layout.addWidget(self.splitter)

    # connect events to handle
    self.tree.itemChanged.connect(self.itemChanged)
    self.tree.itemSelectionChanged.connect(self.itemSelectionChanged)
    self.tree.itemDoubleClicked.connect(self.itemDoubleClicked)

    self.populate_tree()
    self.set_checks()

  def get_obj(self, obj_id):
    if obj_id in self.locals:
      return self.locals[obj_id]
    else:
      return self.remotes[obj_id]

  def itemSelectionChanged(self):
    if not self.tree.selectedItems():
      return

    item = self.tree.selectedItems()[0]
    parent = item.parent()
    if parent is None:
      return

    id1 = item.parent().api_id
    id2 = item.api_id

    try:
      response = network.query("GET", "display/compare/",
                               params={"id1": id1, "id2": id2}, json=False)
      self.textBrowser.setHtml(response)
      self.textBrowser.reload()
    except exceptions.QueryException:
      pass

  def itemDoubleClicked(self, item, column):
    del column

    if item.parent() is None:
      idaapi.jumpto(self.get_obj(item.api_id)['offset'])
      item.setExpanded(not item.isExpanded())

  def itemChanged(self, item, column):
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
          # remote_obj = self.documentation[remote_item.api_id]
          # remote_docs = remote_obj["documentation"]
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

  def should_filter(self, context):
    if self.script_compile:
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
          return True
    return 'Filter' in context and context['Filter']

  def populate_tree(self):
    self.tree.sortItems(self.DOCUMENTATION_SCORE_COLUMN,
                        QtCore.Qt.DescendingOrder)
    self.tree.setSortingEnabled(False)

    for local_id, local_obj in self.locals.items():
      local_ea = local_obj['offset']
      local_name = name_obj(local_obj)

      context = {'Filter': False, 'remote': None}
      context['local'] = {'ea': local_ea, 'name': local_name,
                          # 'docscore': local_obj["documentation_score"],
                          # 'documentation': local_obj['documentation'],
                          'local': True}
      if self.should_filter(context):
        continue

      local_root = MatchTreeWidgetItem(local_id, self.tree)
      local_root.setFlags(QtCore.Qt.ItemIsEnabled |
                          QtCore.Qt.ItemIsSelectable)
      local_root.setText(self.MATCH_NAME_COLUMN, local_name)
      local_root.setForeground(self.MATCH_NAME_COLUMN,
                               self.LOCAL_ELEMENT_COLOR)
      local_root.setToolTip(self.MATCH_NAME_COLUMN, self.LOCAL_ELEMENT_TOOLTIP)
      # local_root.setText(self.MATCH_KEY_COLUMN,
      #                    str(self.documentation[local_id]["match_key"]))

      self.tree.expandItem(local_root)

      for match_obj in local_obj['matches']:
        remote_id = match_obj['to_instance']
        remote_obj = self.remotes[remote_id]
        remote_ea = remote_obj['offset']
        remote_name = name_obj(remote_obj)

        context = {'Filter': False}
        context['local'] = {'ea': local_ea, 'name': local_name,
                            # 'docscore': local_obj["documentation_score"],
                            # 'documentation': local_obj['documentation'],
                            'local': True}
        context['remote'] = {'ea': remote_ea, 'name': remote_name,
                             # 'docscore': remote_obj["documentation_score"],
                             # 'documentation': remote_obj['documentation'],
                             'score': match_obj["score"],
                             'key': match_obj["type"],
                             # TODO: a remote match can also be local
                             'local': False}
        if self.should_filter(context):
          continue

        remote_root = MatchTreeWidgetItem(remote_id, local_root)
        remote_root.setFlags(QtCore.Qt.ItemIsUserCheckable |
                             QtCore.Qt.ItemIsEnabled |
                             QtCore.Qt.ItemIsSelectable)

        remote_root.setText(self.MATCH_NAME_COLUMN, "{0}".format(remote_name))

        if remote_id in self.locals:
          remote_root.setForeground(self.MATCH_NAME_COLUMN,
                                    self.LOCAL_ELEMENT_COLOR)
          remote_root.setToolTip(self.MATCH_NAME_COLUMN,
                                 self.LOCAL_ELEMENT_TOOLTIP)
        else:
          remote_root.setToolTip(self.MATCH_NAME_COLUMN,
                                 self.REMOTE_ELEMENT_TOOLTIP)

        match_score = match_obj['score']
        # TODO: get a real score here
        doc_score = 0
        remote_root.setText(self.MATCH_SCORE_COLUMN,
                            str(round(match_score, 2)))
        remote_root.setText(self.DOCUMENTATION_SCORE_COLUMN,
                            str(round(doc_score, 2)))
        remote_root.setText(self.MATCH_KEY_COLUMN,
                            str(match_obj['type']))
        remote_root.setCheckState(self.CHECKBOX_COLUMN, QtCore.Qt.Unchecked)

    # fake click on first child item so browser won't show a blank page
    root = self.tree.invisibleRootItem()
    if root.childCount():
      if root.child(0).childCount():
        item = root.child(0).child(0)
        item.setSelected(True)
