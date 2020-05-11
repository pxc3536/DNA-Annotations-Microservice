__author__ = 'Paul Chang <pchang3@uchicago.edu>'
# Reference: Vas Vasiliadis of University of Chicago

import sys, os
import time
import driver
import threading
import logging
import boto3
import json
from pathlib import Path
from subprocess import Popen, PIPE
from botocore.exceptions import ClientError
from config import Config

"""A rudimentary timer for coarse-grained profiling
"""
class Timer(object):
  def __init__(self, verbose=True):
    self.verbose = verbose

  def __enter__(self):
    self.start = time.time()
    return self

  def __exit__(self, *args):
    self.end = time.time()
    self.secs = self.end - self.start
    if self.verbose:
      print("Total runtime: {0:.6f} seconds".format(self.secs))

class ProgressPercentage(object):
  '''
  Ref: https://stackoverflow.com/questions/41827963/track-download-progress-of-s3-file-using-boto3-and-callbacks
  '''
  def __init__(self, filepath):
    self._filepath = filepath
    self._size = float(os.path.getsize(filepath))
    self._seen_so_far = 0
    self._lock = threading.Lock()

  def __call__(self, bytes_amount):
    # To simplify, assume this is hooked up to a single filename
    with self._lock:
      self._seen_so_far += bytes_amount
      if self._seen_so_far == self._size:
        try:
          Popen(['rm', '-rf', Path(self._filepath)], cwd='/', stderr=PIPE).wait()
        except OSError as e:
          logging.error(e)
        except ValueError as e:
          logging.error(e)
          
        if len(os.listdir(Path(self._filepath).parents[0])) == 1:
          try:
            Popen(['rm', '-rf', Path(self._filepath).parents[0]], cwd='/', stderr=PIPE).wait()
          except OSError as e:
            logging.error(e)
          except ValueError as e:
            logging.error(e)


if __name__ == '__main__':
  # Call the AnnTools pipeline
  # Ref: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html
  # https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.Python.03.html#GettingStarted.Python.03.03
  # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/dynamodb.html
  if len(sys.argv) > 1:
    with Timer():
      driver.run(sys.argv[1], 'vcf')

    results_bucket = Config.AWS_S3_RESULTS_BUCKET
    fullFilePath = sys.argv[2]
    basePath, userName, job_id, inputFile, myName, user_email = sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7], sys.argv[8]
    resultFile = inputFile.replace('.', '.annot.')
    resultPath = f'{basePath}/jobs/{userName}/{job_id}/{resultFile}'
    resultKey = f'{myName}/{userName}/{job_id}/{resultFile}'
    logFile = f'{inputFile}.count.log'
    logPath = f'{basePath}/jobs/{userName}/{job_id}/{logFile}'
    logKey = f'{myName}/{userName}/{job_id}/{logFile}'

    # Ref: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html
    s3_client = boto3.client('s3', region_name=Config.AWS_REGION_NAME)
    try:
      response = s3_client.upload_file(Filename=resultPath, Bucket=results_bucket, Key=resultKey, Callback=ProgressPercentage(resultPath))
      response = s3_client.upload_file(Filename=logPath, Bucket=results_bucket, Key=logKey, Callback=ProgressPercentage(logPath))
    except ClientError as e:
      logging.error(e)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
    dynamodb = boto3.resource('dynamodb', region_name=Config.AWS_REGION_NAME)
    ann_table = dynamodb.Table(Config.AWS_DYNAMODB_ANNOTATIONS_TABLE)
    try:
      ann_table.update_item(
        Key={
            'job_id': job_id
        },
        UpdateExpression="set s3_key_result_file = :rk, s3_key_log_file=:lk, complete_time=:ct, job_status=:js, s3_results_bucket=:rb",
        ExpressionAttributeValues={
            ':rk': resultKey,
            ':lk': logKey,
            ':ct': int(time.time()),
            ':js': 'COMPLETED',
            ':rb': results_bucket
        }
      )
    except ClientError as e:
      logging.error(e)
    
    data = {
      "job_id": job_id,
      "user_email": user_email
    }

    sns = boto3.resource('sns', region_name=Config.AWS_REGION_NAME)
    topic = sns.Topic(Config.AWS_SNS_JOB_COMPLETE_TOPIC)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
    try:
      response = topic.publish(
        TopicArn=Config.AWS_SNS_JOB_COMPLETE_TOPIC,
        Message=json.dumps(data)
      )
    except ClientError as e:
      logging.error(e)

    archive_data = {
      'job_id': job_id,
      'user_id': userName,
      's3_results_bucket': results_bucket,
      's3_key_result_file': resultKey
    }
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
    topic_archive = sns.Topic(Config.AWS_SNS_JOB_ARCHIVE_TOPIC)
    try:
      response = topic.publish(
        TopicArn=Config.AWS_SNS_JOB_ARCHIVE_TOPIC,
        Message=json.dumps(archive_data)
      )
    except ClientError as e:
      logging.error(e)

  else:
    print("A valid .vcf file must be provided as input to this program.")