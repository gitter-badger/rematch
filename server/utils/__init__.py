import os


class ViewSetTemplateMixin:
  def get_model_name(self):
    return self.__class__.__name__.lower().replace('viewset', '')

  def get_template_names(self):
    name_parts = [self.get_model_name(),
                  "{}.html".format(self.action)]
    template_name = os.path.join(*name_parts)
    return [template_name]
