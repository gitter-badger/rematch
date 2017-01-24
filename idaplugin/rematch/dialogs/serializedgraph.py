import idaapi

class SerializedGraphDialog(idaapi.GraphViewer):
  def __init__(self, *args, **kwargs):
    title = "Remote Function"
    super(SerializedGraphDialog, self).__init__(title, *args, **kwargs)
    self.nodes = None

  def Show(self, nodes):
    self.nodes = nodes
    super(SerializedGraphDialog, self).Show()

  def OnRefresh(self):
    try:
      self.Clear()

      # create nodes
      local_ids = {}
      for node in self.nodes.values():
        node_text = "\n".join(node['assembly'])
        local_id = self.AddNode((node_text, 0xffffff))
        local_ids[node['id']] = local_id

      for node in self.nodes.values():
        local_id = local_ids[node['id']]
        for succ in node['successive']:
          successive_id = local_ids[succ]
          self.AddEdge(local_id, successive_id)
      return True
    except Exception as ex:
      print(ex)

