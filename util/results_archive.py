
import json
import boto3
from botocore.exceptions import ClientError
from config import Config
import logging

def main():
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
  sqs = boto3.resource('sqs', region_name=Config.AWS_REGION_NAME)
  queue = sqs.get_queue_by_name(QueueName=Config.AWS_SQS_JOB_ARCHIVE_QUEUE)
  # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/sqs.html
  queue.set_attributes(
    Attributes={
      'DelaySeconds': Config.JOB_ARCHIVE_QUEUE_DELAY
    }
  )
  while True:
    try:
      messages = queue.receive_messages(
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        )
    except ClientError as e:
      logging.error(e)

    print("Received {0} messages in results_archive...".format(str(len(messages))))

    for message in messages:
      dynamodb = boto3.resource('dynamodb', region_name=Config.AWS_REGION_NAME)
      ann_table = dynamodb.Table(Config.AWS_DYNAMODB_ANNOTATIONS_TABLE)

      try:
        msg_body = json.loads(message.body)
        msg = json.loads(msg_body['Message'])
        job_id = msg['job_id']
        s3_key_result_file = msg['s3_key_result_file']
      except KeyError as e:
        print("Not a valid input message")
        message.delete()
        continue
      except ValueError as e:
        print("Message not in valid json format")
        message.delete()
        continue
      # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.get_item
      try:
        table_response = ann_table.get_item(Key={'job_id': job_id})
      except ClientError as e:
        logging.error(e)
      if table_response['Item']['user_role'] == 'premium_user':
        message.delete()
        continue
      
      s3 = boto3.resource('s3', region_name=Config.AWS_REGION_NAME)
      obj = s3.Object(Config.AWS_S3_RESULTS_BUCKET, s3_key_result_file)
      client = boto3.client('glacier', region_name=Config.AWS_REGION_NAME)
      # https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
      # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.upload_archive
      try:
        glacier_response = client.upload_archive(
          vaultName=Config.AWS_GLACIER_VAULT,
          archiveDescription=json.dumps(msg),
          body=obj.get()['Body'].read()
        )
      except ClientError as e:
        print(e)
        logging.error(e)

      try:
        delete_response = obj.delete()
      except ClientError as e:
        print(e)
        logging.error(e)
      print(delete_response)
      # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
      try:
        ann_table.update_item(
          Key={
            'job_id': job_id
          },
          UpdateExpression="set results_file_archive_id = :id",
          ExpressionAttributeValues={
            ':id': glacier_response['archiveId'],
          }
        )
      except ClientError as e:
        print(e)
        logging.error(e)
      
      message.delete()

if __name__ == "__main__":
  main()