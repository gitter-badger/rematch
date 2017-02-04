import os


class ViewSetTemplateMixin:
  def get_app_name(self):
    return self.__class__.__module__.lower().replace('.views', '')

  def get_model_name(self):
    return self.__class__.__name__.lower().replace('viewset', '')

  def get_template_names(self):
    page = "{}.html".format(self.action)
    model_template_name = os.path.join(self.get_model_name(), page)
    app_template_name = os.path.join(self.get_app_name(), page)
    return [model_template_name, app_template_name, page]
