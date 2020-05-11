# auth.py
#
# Copyright (C) 2011-2018 Vas Vasiliadis
# University of Chicago
#
# Set GAS configuration options based on environment
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import os
import json
import boto3
import base64
from botocore.exceptions import ClientError

basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):  
  GAS_LOG_LEVEL = os.environ['GAS_LOG_LEVEL'] if ('GAS_LOG_LEVEL' in os.environ) else 'INFO'
  GAS_LOG_FILE_PATH = basedir + (os.environ['GAS_LOG_FILE_PATH'] if ('GAS_LOG_FILE_PATH' in os.environ) else "/log")
  GAS_LOG_FILE_NAME = os.environ['GAS_LOG_FILE_NAME'] if ('GAS_LOG_FILE_NAME' in os.environ) else "gas.log"

  SSL_CERT_PATH = os.environ['SSL_CERT_PATH'] if ('SSL_CERT_PATH' in os.environ) else "../ssl/server_dev.crt"
  SSL_KEY_PATH = os.environ['SSL_KEY_PATH'] if ('SSL_KEY_PATH' in os.environ) else "../ssl/server_dev.key"

  AWS_PROFILE_NAME = os.environ['AWS_PROFILE_NAME'] if ('AWS_PROFILE_NAME' in  os.environ) else None
  AWS_REGION_NAME = os.environ['AWS_REGION_NAME'] if ('AWS_REGION_NAME' in  os.environ) else "us-east-1"

  # Get RDS secret from AWS Secrets Manager and construct database URI
  asm = boto3.client('secretsmanager', region_name=AWS_REGION_NAME)
  try:
    asm_response = asm.get_secret_value(SecretId='rds/accounts_database')
    rds_secret = json.loads(asm_response['SecretString'])
  except ClientError as e:
    print(f"Unable to retrieve RDS credentials from AWS Secrets Manager: {e}")
    raise e


  AWS_SIGNED_REQUEST_EXPIRATION = 300  # validity of pre-signed POST requests (in seconds)

  AWS_S3_INPUTS_BUCKET = "gas-inputs"
  AWS_S3_RESULTS_BUCKET = "gas-results"
  # Set the S3 key (object name) prefix to your CNetID
  # Keep the trailing '/' if using my upload code in views.py
  AWS_S3_KEY_PREFIX = "pchang3/"
  AWS_S3_ACL = "private"
  AWS_S3_ENCRYPTION = "AES256"

  AWS_GLACIER_VAULT = "ucmpcs"

  # Queue Names
  AWS_SQS_JOB_ARCHIVE_QUEUE = 'pchang3_job_archive'
  AWS_SQS_JOB_REQUEST_QUEUE = 'pchang3_job_requests'
  AWS_SQS_RESULTS_RESTORE_TOPIC = "pchang3_results_restore"
  AWS_SQS_RESULTS_RESTORE_THAW = "pchang3_results_thaw"

  # Queue Delay Seconds
  JOB_ARCHIVE_QUEUE_DELAY = '10'#'600'

  # Change the ARNs below to reflect your SNS topics
  AWS_SNS_JOB_REQUEST_TOPIC = "arn:aws:sns:us-east-1:127134666975:pchang3_job_requests"
  AWS_SNS_JOB_COMPLETE_TOPIC = "arn:aws:sns:us-east-1:127134666975:pchang3_job_results"
  AWS_SNS_RESULTS_THAW_TOPIC = "arn:aws:sns:us-east-1:127134666975:pchang3_results_thaw"
  AWS_SNS_JOB_ARCHIVE_TOPIC = "arn:aws:sns:us-east-1:127134666975:pchang3_job_archive"

  # Change the table name to your own
  AWS_DYNAMODB_ANNOTATIONS_TABLE = "pchang3_annotations"

  # Stripe API keys
  STRIPE_PUBLIC_KEY = "<your_stripe_TEST_pulic_key>"
  STRIPE_SECRET_KEY = "<your_stripe_TEST_secret_key>"

  # Change the email address to your username
  MAIL_DEFAULT_SENDER = "pchang3@ucmpcs.org"

  FREE_USER_DATA_RETENTION = 600 # time before free user results are archived (in seconds)

  #Stripe API Keys
  STRIPE_PUBLIC_KEY = 'pk_test_LX0VIkkGhzPDKYnNEmTai7dO00dWn5DE8Z'
  STRIPE_SECRET_KEY = 'sk_test_4HqpDn1VnQipnLq6LC7RveLr00rqLAQtG3'

  #Annotations base url
  ANNOTATIONS_URL = 'https://pchang3.ucmpcs.org:4433/annotations/'


class DevelopmentConfig(Config):
  DEBUG = True
  GAS_LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
  DEBUG = False
  GAS_LOG_LEVEL = 'INFO'
  WSGI_SERVER = 'gunicorn.error'
  SSL_CERT_PATH = os.environ['SSL_CERT_PATH'] if ('SSL_CERT_PATH' in os.environ) else "/usr/local/src/ssl/ucmpcs.org.crt"
  SSL_KEY_PATH = os.environ['SSL_KEY_PATH'] if ('SSL_KEY_PATH' in os.environ) else "/usr/local/src/ssl/ucmpcs.org.key"

class StagingConfig(Config):
  STAGING = True

class TestingConfig(Config):
  TESTING = True

### EOF
