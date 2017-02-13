from .. import collectors


class BaseInstance(object):
  def __init__(self, file_version, offset):
    self.file_version = file_version
    self.offset = offset
    self.vectors = set()
    self.annotations = set()

    self.vectors.add(collectors.NameHashVector)
    self.annotations.add(collectors.NameAnnotation)

  def serialize(self):
    vectors = list(collectors.collect(self.offset, self.vectors))
    annotations = list(collectors.collect(self.offset, self.annotations))

    return {"file_version": self.file_version, "type": self.type,
            "offset": self.offset, "vectors": vectors,
            "annotations": annotations}
