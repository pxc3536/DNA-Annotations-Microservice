

import json
import boto3
from botocore.exceptions import ClientError
import logging
from config import Config

def send_email_ses(recipients=None, sender=None, subject=None, body=None):

  ses = boto3.client('ses', region_name=Config.AWS_REGION_NAME)
  # https://docs.aws.amazon.com/ses/latest/DeveloperGuide/send-using-sdk-python.html
  response = ses.send_email(
    Destination = {'ToAddresses': recipients},
    Message={
      'Body': {'Text': {'Charset': "UTF-8", 'Data': body}},
      'Subject': {'Charset': "UTF-8", 'Data': subject},
    },
    Source=sender)
  return response['ResponseMetadata']['HTTPStatusCode']

def main():
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
  sqs = boto3.resource('sqs', region_name=Config.AWS_REGION_NAME)
  queue = sqs.get_queue_by_name(QueueName=Config.AWS_SQS_JOB_RESULT_QUEUE)
  
  while True:
    try:
      messages = queue.receive_messages(
        MaxNumberOfMessages=10,
        WaitTimeSeconds=20,
        )
    except ClientError as e:
      logging.error(e)

    print("Received {0} messages in results_notify...".format(str(len(messages))))

    for message in messages:
      try:
        msg_body = json.loads(message.body)
        msg = json.loads(msg_body['Message'])
        job_id = msg['job_id']
        user_email = msg['user_email']
      except KeyError as e:
        print("Not a valid input message")
        print(msg_body)
        message.delete()
        continue
      except ValueError as e:
        print("Message not in valid json format")
        message.delete()
        continue

      data = f'Job {job_id} is complete \n{Config.ANNOTATIONS_URL}{job_id}'
      send_email_ses(recipients=[user_email], sender=Config.RESULT_SNS_SENDER_EMAIL, subject='Job Complete', body=data)
      
      message.delete()

if __name__ == "__main__":
  main()