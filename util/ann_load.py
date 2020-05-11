import uuid
import time
import json
import sys
import logging
from config import Config

import boto3
from botocore.exceptions import ClientError

sns = boto3.resource('sns', region_name=Config.AWS_REGION_NAME)
topic = sns.Topic(Config.AWS_SNS_JOB_REQUEST_TOPIC)

num_messages = int(sys.argv[1])

for i in range(0, num_messages):
    job_id = int(uuid.uuid4())
    user_id = 'fb007865-60fa-4175-8df5-000000000000'
    data = {
        "job_id": job_id,
        "user_id": user_id,
        "input_file_name": 'test.vcf',
        "s3_inputs_bucket": Config.AWS_S3_INPUTS_BUCKET,
        "s3_key_input_file": f"pchang3/{user_id}/{job_id}/test.vcf",
        "submit_time": int(time.time()),
        "user_role": 'free_user',
        "job_status": "PENDING"
    }
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
    try:
        response = topic.publish(
            TopicArn=Config.AWS_SNS_JOB_REQUEST_TOPIC,
            Message=json.dumps(data)
        )
    except ClientError as e:
        logging.error(e)
    print(response)
    print("Sleeping for 10 seconds ...")

    time.sleep(10)