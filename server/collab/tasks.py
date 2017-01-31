from django.utils.timezone import now
from django.db.models import F
from collab.models import Task, Vector, Match
from collab import matches

from celery import shared_task


@shared_task
def match(task_id):
  try:
    # recording the task has started
    task = Task.objects.filter(id=task_id)
    task.update(status=Task.STATUS_STARTED, progress=0,
                progress_max=len(matches.match_list),
                task_id=match.request.id)

    # get input parameters
    task_values = task.values_list('id', 'source_file_version__file_id',
                                   'source_start', 'source_end',
                                   'source_file_version_id',
                                   'target_project_id', 'target_file_id').get()
    print(task_values)
    (task_id, source_file, source_start, source_end, source_file_version,
     target_project, target_file) = task_values

    source_filter = {'file_id': source_file,
                     'file_version_id': source_file_version}
    if source_start:
      source_filter['instance__offset__gte'] = source_start
    if source_end:
      source_filter['instance__offset__lte'] = source_end
    base_source_vectors = Vector.objects.filter(**source_filter)

    target_filter = {}
    if target_project:
      target_filter = {'file__project_id': target_project}
    elif target_file:
      target_filter = {'file_id': target_file}
    base_target_vectors = Vector.objects.filter(**target_filter)
    base_target_vectors = base_target_vectors.exclude(file_id=source_file)

    print("Running task {}".format(match.request.id))
    # TODO: order might be important here
    for match_type in matches.match_list:
      print(match_type)
      start = now()
      source_vectors = base_source_vectors.filter(type=match_type.vector_type)
      target_vectors = base_target_vectors.filter(type=match_type.vector_type)

      if source_vectors.count() and target_vectors.count():
        match_objs = gen_match_objs(task_id, match_type, source_vectors,
                                    target_vectors)
        Match.objects.bulk_create(match_objs, batch_size=10000)
      print("\tTook: {}".format(now() - start))

      task.update(progress=F('progress') + 1)
  except Exception:
    task.update(status=Task.STATUS_FAILED, finished=now())
    raise

  task.update(status=Task.STATUS_DONE, finished=now())


def gen_match_objs(task_id, match_type, source_vectors, target_vectors):
  matches = match_type.match(source_vectors, target_vectors)
  for source, source_instance, target, target_instance, score in matches:
    mat = Match(task_id=task_id, from_vector_id=source, to_vector_id=target,
                from_instance_id=source_instance,
                to_instance_id=target_instance,
                score=score, type=match_type.match_type)
    yield mat
