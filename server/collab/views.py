from rest_framework import (viewsets, permissions, mixins, decorators, status,
                            response)
from collab.models import (Project, File, FileVersion, Task, Instance, Vector,
                           Match)
from collab.serializers import (ProjectSerializer, FileSerializer,
                                FileVersionSerializer, TaskSerializer,
                                TaskEditSerializer, TaskInstanceSerializer,
                                InstanceVectorSerializer, VectorSerializer,
                                MatchSerializer, SimpleInstanceSerializer)
from collab.permissions import IsOwnerOrReadOnly
from collab import tasks


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


class ProjectViewSet(ViewSetOwnerMixin, viewsets.ModelViewSet):
  queryset = Project.objects.all()
  serializer_class = ProjectSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('created', 'owner', 'name', 'description', 'private')


class FileViewSet(ViewSetOwnerMixin, viewsets.ModelViewSet):
  queryset = File.objects.all()
  serializer_class = FileSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('created', 'owner', 'project', 'name', 'description',
                   'md5hash')

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


class TaskViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                  mixins.DestroyModelMixin, mixins.ListModelMixin,
                  viewsets.GenericViewSet):
  queryset = Task.objects.all()
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,
                        IsOwnerOrReadOnly)
  filter_fields = ('task_id', 'created', 'finished', 'owner', 'status')

  def perform_create(self, serializer):
    task = serializer.save(owner=self.request.user)
    tasks.match.delay(task_id=task.id)

  def get_serializer_class(self):
    serializer_class = TaskSerializer
    if self.request.method in ('PATCH', 'PUT'):
      serializer_class = TaskEditSerializer
    return serializer_class

  @decorators.detail_route(url_path="matches")
  def matches(self, request, pk):
    del request

    task = self.get_object()

    # include local matches (created for specified file_version and are a
    # 'from_instance' match). for those, include the match objects themselves
    instances = Instance.objects.filter(file_version=task.source_file_version)
    instances = instances.exclude(from_matches=None)
    serializer = TaskInstanceSerializer(task.id, instances, many=True)
    # TODO: this shouldn't be needed here
    serializer.is_valid()
    local_instances_data = serializer.data

    # include remote matches (are a 'to_instance' match), those are referenced
    # by match records of local instances
    instances = Instance.objects.filter(to_matches__task=task)
    serializer = SimpleInstanceSerializer(instances, many=True)
    remote_instances_data = serializer.data

    data = {'local': local_instances_data, 'remote': remote_instances_data}
    return response.Response(data)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
  queryset = Match.objects.all()
  serializer_class = MatchSerializer
  filter_fields = ('task', 'type', 'score')


class InstanceViewSet(ViewSetManyAllowedMixin, ViewSetOwnerMixin,
                      viewsets.ModelViewSet):
  queryset = Instance.objects.all()
  serializer_class = InstanceVectorSerializer
  filter_fields = ('owner', 'file_version', 'type')


class VectorViewSet(ViewSetManyAllowedMixin, viewsets.ModelViewSet):
  queryset = Vector.objects.all()
  serializer_class = VectorSerializer
  permission_classes = (permissions.IsAuthenticatedOrReadOnly,)
  filter_fields = ('instance', 'file_version', 'type', 'type_version')

  @staticmethod
  def perform_create(serializer):
    file_version = serializer.validated_data['instance'].file_version
    serializer.save(file_version=file_version)
