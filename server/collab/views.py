from rest_framework import (viewsets, permissions, mixins, decorators, status,
                            response)
from collab.models import (Project, File, FileVersion, Task, Instance, Vector,
                           Match)
from collab.serializers import (ProjectSerializer, FileSerializer,
                                FileVersionSerializer, TaskSerializer,
                                InstanceSerializer, VectorSerializer,
                                MatchSerializer)
from collab.permissions import IsOwnerOrReadOnly
from collab import tasks
from rematch.template import ViewSetTemplateMixin


class ViewSetOwnerMixin(object):
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,
                        IsOwnerOrReadOnly)

  def perform_create(self, serializer):
    serializer.save(owner=self.request.user)


class ViewSetManyAllowedMixin(object):
  def get_serializer(self, *args, **kwargs):
    if "data" in kwargs:
      data = kwargs["data"]

      if isinstance(data, list):
        kwargs["many"] = True

    return super(ViewSetManyAllowedMixin, self).get_serializer(*args, **kwargs)


class ProjectViewSet(ViewSetOwnerMixin, ViewSetTemplateMixin,
                     viewsets.ModelViewSet):
  queryset = Project.objects.all()
  serializer_class = ProjectSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('created', 'owner', 'name', 'description', 'private')
  template_fields = ('name', 'description', 'private', 'created', 'owner')


class FileViewSet(ViewSetOwnerMixin, ViewSetTemplateMixin,
                  viewsets.ModelViewSet):
  queryset = File.objects.all()
  serializer_class = FileSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('created', 'owner', 'project', 'name', 'description',
                   'md5hash')
  template_fields = ('name', 'md5hash', 'description', 'project', 'created',
                     'owner', 'file')

  @decorators.detail_route(url_path="file_version/(?P<md5hash>[0-9A-Fa-f]+)",
                           methods=['GET', 'POST'])
  def file_version(self, request, pk, md5hash):
    del pk
    file = self.get_object()

    if request.method == 'POST':
      file_version, created = \
        FileVersion.objects.get_or_create(md5hash=md5hash, file=file)
    else:
      file_version = FileVersion.objects.get(md5hash=md5hash, file=file)
      created = False

    serializer = FileVersionSerializer(file_version)

    resp_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    response_data = serializer.data
    response_data['newly_created'] = created
    return response.Response(response_data, status=resp_status)


class FileVersionViewSet(viewsets.ModelViewSet):
  queryset = FileVersion.objects.all()
  serializer_class = FileVersionSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('id', 'file', 'md5hash')


class TaskViewSet(ViewSetTemplateMixin, mixins.CreateModelMixin,
                  mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                  mixins.ListModelMixin, viewsets.GenericViewSet):
  queryset = Task.objects.all()
  serializer_class = TaskSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,
                        IsOwnerOrReadOnly)
  filter_fields = ('task_id', 'created', 'finished', 'owner', 'status')

  def perform_create(self, serializer):
    task = serializer.save(owner=self.request.user)
    tasks.match.delay(task_id=task.id)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
  queryset = Match.objects.all()
  serializer_class = MatchSerializer
  filter_fields = ('task', 'type', 'score')


class InstanceViewSet(ViewSetManyAllowedMixin, ViewSetOwnerMixin,
                      ViewSetTemplateMixin, viewsets.ModelViewSet):
  queryset = Instance.objects.all()
  serializer_class = InstanceSerializer
  filter_fields = ('owner', 'file_version', 'type')


class VectorViewSet(ViewSetManyAllowedMixin, ViewSetTemplateMixin,
                    viewsets.ModelViewSet):
  queryset = Vector.objects.all()
  serializer_class = VectorSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('instance', 'file_version', 'type', 'type_version')

  @staticmethod
  def perform_create(serializer):
    file_version = serializer.validated_data['instance'].file_version
    serializer.save(file_version=file_version)
