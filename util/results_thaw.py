
import json
import boto3
from botocore.exceptions import ClientError
from config import Config
import logging


def main():
    s3 = boto3.resource('s3', region_name=Config.AWS_REGION_NAME)
    sqs = boto3.resource('sqs', region_name=Config.AWS_REGION_NAME)
    queue = sqs.get_queue_by_name(QueueName=Config.AWS_SQS_RESULTS_RESTORE_THAW)
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

        print("Received {0} messages in results_thaw...".format(str(len(messages))))

        for message in messages:
            try:
                msg_body = json.loads(message.body)
                msg = json.loads(msg_body['Message'])
                retrieval_job_id = msg['JobId']
                archive_id = msg['ArchiveId']
                job_id = json.loads(msg['JobDescription'])['job_id']
            except KeyError as e:
                print("Not a valid input message")
                logging.error(e)
                message.delete()
                continue
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.get_job_output
            thaw_response = glacier.get_job_output(
                vaultName=Config.AWS_GLACIER_VAULT,
                jobId=retrieval_job_id,
            )
            print(thaw_response)
            archive_description = json.loads(thaw_response['archiveDescription'])
            s3_key_result_file = archive_description['s3_key_result_file']
            # https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
            obj = s3.Object(Config.AWS_S3_RESULTS_BUCKET, s3_key_result_file)
            obj.put(Body=thaw_response['body'].read())
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.delete_archive
            del_response = glacier.delete_archive(
                vaultName=Config.AWS_GLACIER_VAULT,
                archiveId=archive_id
            )
            print(del_response)
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
            ann_table.update_item(
                Key={
                    'job_id': job_id
                },
                UpdateExpression='REMOVE results_file_archive_id',
            )
            message.delete()


if __name__ == "__main__":
    main()