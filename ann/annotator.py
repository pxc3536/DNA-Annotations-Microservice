import uuid, base64, json, logging, time
import sys, os, base64, datetime, hashlib, hmac
import threading
from pathlib import Path
from subprocess import Popen, PIPE
import boto3, botocore
from botocore.exceptions import ClientError
from config import Config

class ProgressPercentage(object):
  '''
  Ref: https://stackoverflow.com/questions/41827963/track-download-progress-of-s3-file-using-boto3-and-callbacks
  '''
  def __init__(self, myName, fileSize, fullFilePath, basePath, userName, job_id, fileName, user_email):
    self._fullFilePath = fullFilePath
    self._size = float(fileSize)
    self._seen_so_far = 0
    self._lock = threading.Lock()
    self.basePath = basePath
    self.userName = userName
    self.job_id = job_id
    self.fileName = fileName
    self.myName = myName
    self.user_email = user_email


  def __call__(self, bytes_amount):
    # To simplify, assume this is hooked up to a single filename
    with self._lock:
      self._seen_so_far += bytes_amount
      if self._seen_so_far == self._size:
        # https://docs.python.org/3/library/subprocess.html
        try:
          Popen(['python', 'run.py', f'../jobs/{self.userName}/{self.job_id}/{self.fileName}', \
          f'{self._fullFilePath}', f'{self.basePath}', f'{self.userName}', f'{self.job_id}', f'{self.fileName}', f'{self.myName}', f'{self.user_email}'], \
          cwd=f'{self.basePath}/anntools/', stderr=PIPE)
        except OSError as e:
          logging.error(e)
        except ValueError as e:
          logging.error(e)

# References
# https://docs.python.org/3/library/subprocess.html
# https://stackoverflow.com/questions/793858/how-to-mkdir-only-if-a-dir-does-not-already-exist
# https://medium.com/@ageitgey/python-3-quick-tip-the-easy-way-to-deal-with-file-paths-on-windows-mac-and-linux-11a072b58d5f
# https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
# MPCS 51083 Class Exercise https://docs.google.com/document/d/1JNXr4FE8WKAsO6oI0HBtmwNQ7u__J45feOwnb7d1qjM/edit
def main():
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
  sqs = boto3.resource('sqs', region_name=Config.AWS_REGION_NAME)
  queue = sqs.get_queue_by_name(QueueName=Config.AWS_SQS_JOB_REQUEST_QUEUE)
  
  while True:
    try:
      messages = queue.receive_messages(
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        )
    except ClientError as e:
      logging.error(e)

    print("Received {0} messages...".format(str(len(messages))))

    for message in messages:
      try:
        msg_body = json.loads(message.body)
        bucket = msg_body['s3_inputs_bucket']
        key = msg_body["s3_key_input_file"]
        user_email = msg_body['user_email']
      except KeyError as e:
        print("Not a valid input message")
        message.delete()
        continue
      except ValueError as e:
        print("Message not in valid json format")
        message.delete()
        continue
      
      basePath = os.path.dirname(os.path.abspath(__file__))
      myName, userName, job_id, fileName = key.split('/')
      fullFilePath = f'{basePath}/jobs/{userName}/{job_id}/{fileName}'

      # https://docs.python.org/3/library/subprocess.html
      # https://stackoverflow.com/questions/793858/how-to-mkdir-only-if-a-dir-does-not-already-exist
      # https://medium.com/@ageitgey/python-3-quick-tip-the-easy-way-to-deal-with-file-paths-on-windows-mac-and-linux-11a072b58d5f
      try:
        Popen(['mkdir', '-p', Path(f'{userName}/{job_id}')], cwd=Path(f'{basePath}/jobs')).wait()
        Popen(['touch', Path(f'{userName}/{job_id}/{fileName}')], cwd=Path(f'{basePath}/jobs')).wait()
      except OSError as e:
        logging.error(e)
      except ValueError as e:
        logging.error(e)

      s3 = boto3.resource('s3', region_name=Config.AWS_REGION_NAME)
      # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
      try:
        fileSize = s3.meta.client.head_object(Bucket=bucket, Key=key)['ContentLength']
        s3.meta.client.download_file(bucket, key, fullFilePath, Callback=ProgressPercentage( \
          myName, fileSize, fullFilePath, basePath, userName, job_id, fileName, user_email) \
        )
      except ClientError as e:
        logging.error(e)

      # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.put_item
      dynamodb = boto3.resource('dynamodb', region_name=Config.AWS_REGION_NAME)
      ann_table = dynamodb.Table(Config.AWS_DYNAMODB_ANNOTATIONS_TABLE)
      try:
        ann_table.update_item(
          Key={
              'job_id': job_id
          },
          UpdateExpression="set job_status=:njs",
          ConditionExpression="job_status = :ojs",
          ExpressionAttributeValues={
              ':njs': 'RUNNING',
              ':ojs': 'PENDING'
          }
        )
      except ClientError as e:
        logging.error(e)
      
      message.delete()

if __name__ == "__main__":
  main()