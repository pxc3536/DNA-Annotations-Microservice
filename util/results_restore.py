
import json
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from config import Config
import logging


def main():
    sqs = boto3.resource('sqs', region_name=Config.AWS_REGION_NAME)
    queue = sqs.get_queue_by_name(QueueName=Config.AWS_SQS_RESULTS_RESTORE_TOPIC)
    dynamodb = boto3.resource('dynamodb', region_name=Config.AWS_REGION_NAME)
    ann_table = dynamodb.Table(Config.AWS_DYNAMODB_ANNOTATIONS_TABLE)
    glacier = boto3.client('glacier', region_name=Config.AWS_REGION_NAME)

    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
    while True:
        messages = None
        try:
            messages = queue.receive_messages(
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )
        except ClientError as e:
            logging.error(e)

        print("Received {0} messages in results_restore...".format(str(len(messages))))

        for message in messages:
            try:
                msg_body = json.loads(message.body)
                msg = json.loads(msg_body['Message'])
                user_id = msg['user_id']
            except KeyError as e:
                print("Not a valid input message")
                logging.error(e)
                message.delete()
                continue

            annotations = None
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.query
            try:
                annotations = ann_table.query(
                    IndexName='user_id_index',
                    KeyConditionExpression=Key('user_id').eq(user_id)
                )
            except ClientError as e:
                logging.error(e)

            for annotation in annotations['Items']:
                try:
                    ArchiveId = annotation['results_file_archive_id']
                except KeyError:
                    continue
                # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
                try:
                    ann_table.update_item(
                        Key={
                            'job_id': annotation['job_id']
                        },
                        UpdateExpression="set user_role = :r",
                        ExpressionAttributeValues={
                            ':r': "premium_user"
                        }
                    )
                except ClientError as e:
                    logging.error(e)

                glacier_response = None
                # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.initiate_job
                try:
                    glacier_response = glacier.initiate_job(
                        vaultName=Config.AWS_GLACIER_VAULT,
                        jobParameters={
                            'Tier': 'Expedited',
                            'SNSTopic': Config.AWS_SNS_RESULTS_THAW_TOPIC,
                            'Description': json.dumps({"job_id": annotation['job_id'], "user_id": user_id}),
                            'Type': 'archive-retrieval',
                            'ArchiveId': ArchiveId
                        },
                    )
                except ClientError as e:
                    logging.error(e)
                    if e.response['Error']['Code'] == 'InsufficientCapacityException':
                        try:
                            glacier_response = glacier.initiate_job(
                                vaultName=Config.AWS_GLACIER_VAULT,
                                jobParameters={
                                    'Tier': 'Standard',
                                    'SNSTopic': Config.AWS_SNS_RESULTS_THAW_TOPIC,
                                    'Description': json.dumps({"job_id": annotation['job_id'], "user_id": user_id}),
                                    'Type': 'archive-retrieval',
                                    'ArchiveId': ArchiveId
                                },
                            )
                        except ClientError as e:
                            print(e.response['Error']['Code'])
                            logging.error(e)
                print(glacier_response)
            message.delete()


if __name__ == "__main__":
    main()
