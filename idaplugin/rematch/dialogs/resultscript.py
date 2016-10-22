import os

from ..idasix import QtWidgets

from .. import utils


class ResultScriptDialog(QtWidgets.QDialog):
  def __init__(self, script_code):
    super(ResultScriptDialog, self).__init__()
    self.setWindowTitle("Result script")

    self.scripts_path = utils.getPluginPath('scripts')

    self.script_txt = QtWidgets.QTextEdit()
    self.script_txt.setText(script_code)
    self.statusLbl = QtWidgets.QLabel()
    self.statusLbl.setStyleSheet("color: red;")
    self.cb = QtWidgets.QComboBox()

    if not os.path.exists(self.scripts_path):
      os.makedirs(self.scripts_path)

    for script_name in os.listdir(self.scripts_path):
      if script_name.endswith(".py"):
        self.cb.addItem(script_name)

    if self.cb.count() > 0:
      default_script = os.path.join(self.scripts_path, self.cb.itemText(0))
      with open(default_script, "r") as fh:
        data = fh.read()
        self.scriptTxt.setText(data)

    size_policy = QtWidgets.Qsize_policy(QtWidgets.Qsize_policy.Fixed,
                                         QtWidgets.Qsize_policy.Fixed)

    new_btn = QtWidgets.QPushButton("&New")
    save_btn = QtWidgets.QPushButton("&Save")
    apply_btn = QtWidgets.QPushButton("&Apply")
    cancel_btn = QtWidgets.QPushButton("&Cancel")

    new_btn.setsize_policy(size_policy)
    save_btn.setsize_policy(size_policy)
    apply_btn.setsize_policy(size_policy)
    cancel_btn.setsize_policy(size_policy)

    button_lyt = QtWidgets.GridBoxLayout()
    button_lyt.addWidget(new_btn, 0, 0)
    button_lyt.addWidget(save_btn, 0, 1)
    button_lyt.addWidget(apply_btn, 1, 0)
    button_lyt.addWidget(cancel_btn, 1, 1)

    apply_btn.clicked.connect(self.validate)
    cancel_btn.clicked.connect(self.reject)
    save_btn.clicked.connect(self.SaveFile)
    new_btn.clicked.connect(self.NewFilter)

    self.cb.resize(200, 200)

    help_tooltip = ["While executing the script code, the following context "
                    "variables are available:",
                    "<b>Filter</b>: defaults to False. determines wether "
                    "this item should be filtered out (you should change "
                    "this)",
                    "<b>Errors</b>: defaults to 'filter'. when a runtime "
                    "error occures in script code this will help determine "
                    "how to continue.",
                    "There are several valid values:",
                    " - '<b>filter</b>': filter this function using whatever "
                    "value was in Filter at the time of the error",
                    " - '<b>silent_filter</b>': filter using whatever value "
                    "in Filter, but do not present error messages.",
                    " - '<b>break</b>': handle runtime errors as "
                    "non-continual. stop presenting matches immidiately.",
                    " - '<b>hide</b>': hide all functions in which a "
                    "filtering error occured, after displaying a warning.",
                    " - '<b>show</b>': show all functions in which a "
                    "filtering error occured, after displaying a warning.",
                    "",
                    "When filtering a match function(a leaf) both the local "
                    "and match variables exist.",
                    "When filtering a local function(a tree root) only the "
                    "local variable exist, and remote equals to None.",
                    "The local variable describes the local function (tree "
                    "root), and the match variable describes the function "
                    "matched to the local one(the local root's leaf).",
                    "both the local and match variables, if exist, are "
                    "dictionaries containing these keys:",
                    "<b>'ea'</b>: effective address of function",
                    "<b>'name'</b>: name of function (or a string of ea in "
                    "hexadecimal if no name defined for match functions)",
                    "<b>'docscore'</b>: a float between 0 and 1.0 "
                    "representing the documentation score of function",
                    "<b>'score'</b>: (INTERNAL) a float between 0 and 1.0 "
                    "representing the match score of this function and the "
                    "core element",
                    "<b>'key'</b>: (INTERNAL) the match type.",
                    "<b>'documentation'</b>: (INTERNAL) available "
                    "documentation for each line of code",
                    "<b>'local'</b> : True if this function originated from "
                    "the local binary (for when a local function matched "
                    "another local function).",
                    "",
                    "Note: variables marked as INTERNAL are likely to change "
                    "in format, content and values without prior notice. your "
                    "code may break.",
                    "user discretion is advised."]
    help_tooltip = "\n".join(help_tooltip)

    self.layout = QtWidgets.QVBoxLayout()

    helpLbl = QtWidgets.QLabel("Insert native python code to filter matches:"
                               "\n(Hover for more information)")
    helpLbl.setToolTip(help_tooltip)

    ComboLayout = QtWidgets.QHBoxLayout()
    ComboLayoutText = QtWidgets.QLabel("Script - ")
    ComboLayout.addWidget(ComboLayoutText)
    ComboLayout.addWidget(self.cb)

    self.layout.addWidget(helpLbl)
    self.layout.addLayout(ComboLayout)
    self.layout.addWidget(self.script_txt)
    self.layout.addWidget(self.statusLbl)
    self.layout.addLayout(button_lyt)

    self.setLayout(self.layout)
    self.cb.currentIndexChanged.connect(self.ComboBoxChange)

  def SaveFile(self):
    fpath = QtWidgets.QFileDialog.getSaveFileName(self, "Save Data File", ""
                                                  "Python files (*.py)")
    if not fpath:
      return

    with open(fpath, 'w') as fh:
      fh.write(self.script_txt.toPlainText())

    self.cb.clear()
    for file in os.listdir(self.scripts_path):
      if file.endswith(".py"):
        self.cb.addItem(file)
        # TODO: set the default as the file juss saved

  def new_filter(self):
    if not self.cb.itemText(0) == "New":
      self.cb.insertItem(0, "New")
      self.cb.setCurrentIndex(0)

  def ComboBoxChange(self, new_value):
    fpath = os.path.join(self.scripts_path, new_value)
    if os.path.isfile(fpath):
      with open(fpath, "r") as myfile:
        data = myfile.read()
    else:
      data = ""
    self.script_txt.setText(data)

  def get_filter(self):
    return self.script_txt.toPlainText()

  def validate(self):
    try:
      compile(self.getFilter(), '<input>', 'exec')
    except Exception as ex:
      self.statusLbl.setText(str(ex))
    else:
      self.accept()
