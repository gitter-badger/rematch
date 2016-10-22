import idaapi
import idc

from .. idasix import QtGui, QtWidgets, QtCore

from . import base
from .. import network
from .. import exceptions

from . import resultscript


def name_obj(obj):
  return obj["name"] if obj["name"] else "sub_{0:X}".format(obj['ea'])


class MatchTreeWidgetItem(QtWidgets.QTreeWidgetItem):
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


# TODO: replace with connections
# this is supposed to catch typing in the tree widget
# and redirect those to the search text box
# TODO: create a search tree qwidget that has the search text box built into it
class SearchTreeWidget(QtWidgets.QTreeWidget):
  def __init__(self, search_box, match_column, *args, **kwargs):
    super(SearchTreeWidget, self).__init__(*args, **kwargs)
    self.search_box = search_box
    self.match_column = match_column
    self.search_box.textEdited.connect(self.search)

  def keyPressEvent(self, event):
    super(SearchTreeWidget, self).keyPressEvent(self, event)
    if event.text():
      self.search_box.keyPressEvent(event)

  def search(self, text):
    if not text:
      return

    root = self.invisibleRootItem()

    # search in the local elments first
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      if text.lower() in local_item.text(self.match_column).lower():
        local_item.setSelected(True)
        self.setCurrentItem(local_item, self.match_column)
        return

    # search in the remote elments
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        if text.lower() in remote_item.text(self.match_column).lower():
          remote_item.setSelected(True)
          self.setCurrentItem(remote_item, self.match_column)
          return


class MatchResultDialog(base.BaseDialog):
  MATCH_NAME_COLUMN = 0
  CHECKBOX_COLUMN = 0
  MATCH_SCORE_COLUMN = 1
  DOCUMENTATION_SCORE_COLUMN = 2
  MATCH_KEY_COLUMN = 3

  LOCAL_ELEMENT_COLOR = QtGui.QBrush(QtGui.QColor(0x00, 0x00, 0xFF))
  LOCAL_ELEMENT_TOOLTIP = "Local function"
  REMOTE_ELEMENT_TOOLTIP = "Remote function"

  def __init__(self, task_id, **kwargs):
    super(MatchResultDialog, self).__init__(**kwargs)

    self.task_id = task_id

    self.matches = network.query("GET", "collab/matches",
                                 params={'task': self.task_id}, json=True)

    local_instance_ids = [match['from_instance'] for match in self.matches]
    response = network.query("GET", "collab/instances/",
                             params={"id": local_instance_ids}, json=True)
    self.local_instances = {data['id']: data for data in response}

    remote_instance_ids = [match['from_instance'] for match in self.matches]
    response = network.query("GET", "collab/instances/",
                             params={"id": remote_instance_ids}, json=True)
    self.remote_instances = {data['id']: data for data in response}

    # instance_ids = local_instance_ids + remote_instance_ids
    # response = network.query("GET", "collab/annotations/",
    #                          params={"instance": instance_ids}, json=True)
    # self.annotations = {data['instance']: data for data in response}

    self.updating_selects = False

    self.script_code = ("# Filter out any function with "
                        "a name that starts with 'sub_'\n"
                        "if remote:\n"
                        "  this = remote\n"
                        "else:\n"
                        "  this = local\n"
                        "if this['name'].startswith('sub_'):\n"
                        "  Filter = True")
    self.script_compile = None
    self.script_dialog = None

    # buttons
    self.btn_set = QtWidgets.QPushButton('&Select best')
    self.btn_clear = QtWidgets.QPushButton('&Clear')
    self.btn_filter = QtWidgets.QPushButton('Fi&lter')
    self.btn_apply = QtWidgets.QPushButton('&Apply Matches')

    size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                        QtWidgets.QSizePolicy.Fixed)
    self.btn_set.setSizePolicy(size_policy)
    self.btn_clear.setSizePolicy(size_policy)
    self.btn_filter.setSizePolicy(size_policy)
    self.btn_apply.setSizePolicy(size_policy)

    # buttons layout
    self.hlayoutButtons = QtWidgets.QHBoxLayout()
    # self.hlayoutButtons.setDirection(QtWidgets.QHBoxLayout.LeftToRight)
    self.hlayoutButtons.addWidget(self.btn_set)
    self.hlayoutButtons.addWidget(self.btn_clear)
    self.hlayoutButtons.addWidget(self.btn_filter)
    self.hlayoutButtons.addWidget(self.btn_apply)

    self.hlayoutButtons.setAlignment(self.btn_set, QtCore.Qt.AlignLeft)
    self.hlayoutButtons.setAlignment(self.btn_clear, QtCore.Qt.AlignLeft)
    self.hlayoutButtons.setAlignment(self.btn_filter, QtCore.Qt.AlignLeft)
    self.hlayoutButtons.setAlignment(self.btn_apply, QtCore.Qt.AlignRight)
    self.hlayoutButtons.totalSizeHint()

    # matches tree
    self.search_box = QtWidgets.QLineEdit()
    self.tree = SearchTreeWidget(search_box=self.search_box,
                                 match_column=self.MATCH_NAME_COLUMN)

    # tree columns
    self.tree.setHeaderLabels(("Function", "Score", "Doc. Score", "Match Key"))

    # other tree properties
    self.tree.setAutoFillBackground(False)
    self.tree.setFrameShape(QtWidgets.QFrame.NoFrame)
    self.tree.setTabKeyNavigation(True)
    self.tree.setProperty("showDropIndicator", False)
    self.tree.setAlternatingRowColors(True)
    self.tree.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
    self.tree.setRootIsDecorated(True)
    self.tree.setUniformRowHeights(False)
    self.tree.setMinimumSize(QtCore.QSize(0, 16777215))
    self.tree.setStyleSheet("QWidget {color: #000000;}")

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

    self.populate_tree()
    self.tree.header().setDefaultSectionSize(20)
    self.tree.resizeColumnToContents(self.MATCH_SCORE_COLUMN)
    self.tree.resizeColumnToContents(self.DOCUMENTATION_SCORE_COLUMN)
    self.tree.setColumnWidth(self.MATCH_NAME_COLUMN, 150)

    # connect events to handle
    self.tree.itemChanged.connect(self.itemChanged)
    self.tree.itemSelectionChanged.connect(self.itemSelectionChanged)
    self.tree.itemDoubleClicked.connect(self.itemDoubleClicked)

    self.btn_set.clicked.connect(self.slotSetChecks)
    self.btn_clear.clicked.connect(self.slotClearChecks)
    self.btn_filter.clicked.connect(self.slotFilter)
    self.btn_apply.clicked.connect(self.slotApplyMatches)

  def itemSelectionChanged(self):
    if not self.tree.selectedItems():
      return

    item = self.tree.selectedItems()[0]
    parent = item.parent()
    if parent is None:
      return

    id1 = item.parent().id
    id2 = item.id

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
      idaapi.jumpto(item.ea)
      item.setExpanded(not item.isExpanded())

  def itemChanged(self, item, column):
    # (is checkbox column?)
    if not column == self.CHECKBOX_COLUMN:
      return

    parent = item.parent()
    if parent is None:
      return

    if parent.childCount() <= 1:
      return

    if self.updating_selects:
      return

    self.updating_selects = True

    item_index = parent.indexOfChild(item)
    for i in range(parent.childCount()):
      if i != item_index:
        curr_child = parent.child(i)
        curr_child.setCheckState(self.CHECKBOX_COLUMN,
                                 QtCore.Qt.CheckState.Unchecked)

    self.updating_selects = False

  def slotFilter(self):
    self.script_dialog = resultscript.ResultScriptDialog(self.script_code)
    self.script_dialog.accepted.connect(self.slotFilterUpdate)
    self.script_dialog.show()

  def slotFilterUpdate(self):
    self.script_code = self.script_dialog.getFilter()
    self.script_dialog = None

    self.script_compile = compile(self.script_code, '<input>', 'exec')

    self.tree.clear()
    self.populate_tree()

  def slotApplyMatches(self):
    root = self.tree.invisibleRootItem()
    apply_pbar = QtWidgets.QProgressDialog("", "&Cancel", 0, root.childCount())
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        if remote_item.checkState(self.CHECKBOX_COLUMN):
          # TODO: apply metches
          # remote_obj = self.documentation[remote_item.id]["documentation"]
          # apply_documentation(local_item.ea, remote_obj)
          break
      apply_pbar.setValue(apply_pbar.value() + 1)

    # refresh ida's views
    # _idaapi.refresh_idaview_anyway()

  def slotClearChecks(self):
    root = self.tree.invisibleRootItem()
    for local_index in range(root.childCount()):
      local_item = root.child(local_index)
      for remote_index in range(local_item.childCount()):
        remote_item = local_item.child(remote_index)
        remote_item.setCheckState(self.CHECKBOX_COLUMN,
                                  QtCore.Qt.CheckState.Unchecked)

  def slotSetChecks(self):
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
        remote_item.setCheckState(self.CHECKBOX_COLUMN,
                                  QtCore.Qt.CheckState.Checked)

  def shouldFilter(self, context):
    if self.script_compile:
      try:
        exec(self.script_compile, context)
      except Exception as ex:
        idc.Warning("Filter function encountered a runtime error: {}.\n"
                    "proceeding with intermidiate Filter value".format(ex))
    return 'Filter' in context and context['Filter']

  def populate_tree(self):
    self.tree.sortItems(self.DOCUMENTATION_SCORE_COLUMN,
                        QtCore.Qt.DescendingOrder)
    self.tree.setSortingEnabled(False)

    for local_id, remotes in self.matches:
      local_obj = self.documentation[local_id]
      local_ea = self.rev_elements[local_id]
      local_name = name_obj(local_obj)

      context = {'Filter': False, 'remote': None}
      context['local'] = {'ea': local_ea, 'name': local_name,
                          'docscore': local_obj["documentation_score"],
                          'documentation': local_obj['documentation'],
                          'score': local_obj["match_score"],
                          'key': local_obj["match_key"], 'local': True}
      if self.shouldFilter(context):
        continue

      local_root = MatchTreeWidgetItem(self.tree)
      local_root.setFlags(QtCore.Qt.ItemIsEnabled)
      local_root.setText(self.MATCH_NAME_COLUMN, local_name)
      local_root.setForeground(self.MATCH_NAME_COLUMN,
                               self.LOCAL_ELEMENT_COLOR)
      local_root.setToolTip(self.MATCH_NAME_COLUMN, self.LOCAL_ELEMENT_TOOLTIP)
      local_root.setText(self.MATCH_KEY_COLUMN,
                         str(self.documentation[local_id]["match_key"]))
      local_root.id = local_id
      local_root.ea = local_ea

      self.tree.expandItem(local_root)

      remote_root = None
      for remote_id in remotes:
        remote_obj = self.documentation[remote_id]
        remote_ea = remote_obj['offset']
        remote_name = name_obj(remote_obj)

        context = {'Filter': False}
        context['local'] = {'ea': local_ea, 'name': local_name,
                            'docscore': local_obj["documentation_score"],
                            'documentation': local_obj['documentation'],
                            'score': local_obj["match_score"],
                            'key': local_obj["match_key"], 'local': True}
        context['remote'] = {'ea': remote_ea, 'name': remote_name,
                             'docscore': remote_obj["documentation_score"],
                             'documentation': remote_obj['documentation'],
                             'score': remote_obj["match_score"],
                             'key': local_obj["match_key"],
                             'local': remote_id in self.rev_elements.keys()}
        if self.shouldFilter(context):
          continue

        remote_root = MatchTreeWidgetItem(local_root)
        remote_root.id = remote_id
        remote_root.setFlags(QtCore.Qt.ItemIsUserCheckable |
                             QtCore.Qt.ItemIsEnabled |
                             QtCore.Qt.ItemIsSelectable)

        remote_root.setText(self.MATCH_NAME_COLUMN, "{0}".format(remote_name))
        if remote_id in self.rev_elements.keys():
          remote_root.setForeground(self.MATCH_NAME_COLUMN,
                                    self.LOCAL_ELEMENT_COLOR)
          remote_root.setToolTip(self.MATCH_NAME_COLUMN,
                                 self.LOCAL_ELEMENT_TOOLTIP)
        else:
          remote_root.setToolTip(self.MATCH_NAME_COLUMN,
                                 self.REMOTE_ELEMENT_TOOLTIP)

        match_score = (remote_obj["match_score"] * local_obj["match_score"] *
                       100)
        doc_score = remote_obj["documentation_score"] * 100
        remote_root.setText(self.MATCH_SCORE_COLUMN,
                            str(round(match_score, 2)))
        remote_root.setText(self.DOCUMENTATION_SCORE_COLUMN,
                            str(round(doc_score, 2)))
        remote_root.setText(self.MATCH_KEY_COLUMN,
                            str(remote_obj["match_key"]))
        remote_root.setCheckState(self.CHECKBOX_COLUMN,
                                  QtCore.Qt.CheckState.Unchecked)

      # autoselect the last (most recent) match possible...
      # TODO: when there's more info we should make better decisions for which
      # is the default match but right now it's the latest
      if remote_root is not None:
        best_child = sorted([local_root.child(i)
                             for i in range(local_root.childCount())])[-1]
        best_child.setCheckState(self.CHECKBOX_COLUMN,
                                 QtCore.Qt.CheckState.Checked)

    self.tree.setSortingEnabled(True)
    self.tree.sortItems(self.DOCUMENTATION_SCORE_COLUMN,
                        QtCore.Qt.DescendingOrder)
    # fake click on
    root = self.tree.invisibleRootItem()
    if not root.childCount():
      return

    if root.child(0).childCount():
      item = root.child(0).child(0)
      item.setSelected(True)
      self.itemSelectionChanged()
