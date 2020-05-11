# views.py
#
# Copyright (C) 2011-2018 Vas Vasiliadis
# University of Chicago
#
# Application logic for the GAS
#
##
__author__ = 'Vas Vasiliadis <vas@uchicago.edu>'

import uuid
import time
import json
import logging
from datetime import datetime
import stripe

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

from flask import (abort, flash, redirect, render_template,
  request, session, url_for, jsonify)

from gas import app, db
from decorators import authenticated, is_premium
from auth import get_profile, update_profile


"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document
"""
@app.route('/annotate', methods=['GET'])
@authenticated
def annotate():
  # Source: https://stackoverflow.com/questions/34348639/amazon-aws-s3-browser-based-upload-using-post
  # Create a session client to the S3 service
  s3 = boto3.client('s3',
    region_name=app.config['AWS_REGION_NAME'],
    config=Config(signature_version='s3v4'))

  bucket_name = app.config['AWS_S3_INPUTS_BUCKET']
  user_id = session['primary_identity']
  profile = get_profile(identity_id=user_id)
  role = profile.role

  # Generate unique ID to be used as S3 key (name)
  key_name = app.config['AWS_S3_KEY_PREFIX'] + user_id + '/' + str(uuid.uuid4()) + '/${filename}'

  # Create the redirect URL
  redirect_url = str(request.url) + '/job'

  # Define policy fields/conditions
  encryption = app.config['AWS_S3_ENCRYPTION']
  acl = app.config['AWS_S3_ACL']
  fields = {
    "success_action_redirect": redirect_url,
    "x-amz-server-side-encryption": encryption,
    "acl": acl
  }
  conditions = [
    ["starts-with", "$success_action_redirect", redirect_url],
    {"x-amz-server-side-encryption": encryption},
    {"acl": acl}
  ]

  # Generate the presigned POST call
  try:
    presigned_post = s3.generate_presigned_post(
      Bucket=bucket_name,
      Key=key_name,
      Fields=fields,
      Conditions=conditions,
      ExpiresIn=app.config['AWS_SIGNED_REQUEST_EXPIRATION'])
  except ClientError as e:
    return jsonify({'code': 500, 'status': 'error',
      'message': f'Failed to generate presigned post: {e}'})

  # Render the upload form which will parse/submit the presigned POST
  return render_template('annotate.html', s3_post=presigned_post, role=role)


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.
"""
@app.route('/annotate/job', methods=['GET'])
@authenticated
def create_annotation_job_request():
  # Get bucket name, key, and job ID from the S3 redirect URL
  bucket_name = str(request.args.get('bucket'))
  s3_key = str(request.args.get('key'))

  # Extract the job ID from the S3 key
  job_id = s3_key.split('/')[2]
  input_file = s3_key.split('/')[3]
  user_id = session['primary_identity']
  profile = get_profile(identity_id=session.get('primary_identity'))
  user_email = profile.email

  # Persist job to database
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.put_item
  dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  ann_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])

  data = {
            "job_id": job_id,
            "user_id": user_id,
            "user_email": user_email,
            "input_file_name": input_file,
            "s3_inputs_bucket": bucket_name,
            "s3_key_input_file": s3_key,
            "submit_time": int(time.time()),
            "user_role": profile.role,
            "job_status": "PENDING"
          }
  try:
    ann_table.put_item(Item=data)
  except ClientError as e:
    if e.response['Error']['Code'] == 'ValidationException':
      abort(500)
    abort(500)


  # Send message to request queue
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
  sns = boto3.resource('sns', region_name=app.config['AWS_REGION_NAME'])
  topic = sns.Topic(app.config['AWS_SNS_JOB_REQUEST_TOPIC'])

  try:
    topic.publish(
      TopicArn=app.config['AWS_SNS_JOB_REQUEST_TOPIC'],
      Message=json.dumps(data)
    )
  except ClientError as e:
    abort(500)

  return render_template('annotate_confirm.html', job_id=job_id)


"""List all annotations for the user
"""
@app.route('/annotations', methods=['GET'])
@authenticated
def annotations_list():
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.query
  # Get list of annotations to display
  dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  ann_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
  user_id = session['primary_identity']
  response = None
  try:
    response = ann_table.query(
      IndexName='user_id_index',
      KeyConditionExpression=Key('user_id').eq(user_id)
    )
  except ClientError as e:
    logging.error(e)

  return render_template('annotations.html', annotations=response, time=time)


"""Display details of a specific annotation job
"""
@app.route('/annotations/<id>', methods=['GET'])
@authenticated
def annotation_details(id):
  dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  ann_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
  user_id = session['primary_identity']
  response = None
  try:
    response = ann_table.get_item(Key={'job_id': id})
  except ClientError as e:
    logging.error(e)

  s3_client = boto3.client('s3')

  req_time_epoch = response['Item']['submit_time']
  curr_time_epoch = int(time.time())
  free_expired = False
  req_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(req_time_epoch))
  comp_time = None
  result_presigned_url = None
  input_presigned_url = None

  # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
  if response['Item']['job_status'] == 'COMPLETED':
    try:
      result_presigned_url = s3_client.generate_presigned_url('get_object',
        Params={'Bucket': app.config['AWS_S3_RESULTS_BUCKET'],
                'Key': response['Item']['s3_key_result_file']},
        ExpiresIn=300)
    except ClientError as e:
      logging.error(e)
    try:
      input_presigned_url = s3_client.generate_presigned_url('get_object',
        Params={'Bucket': app.config['AWS_S3_INPUTS_BUCKET'],
                'Key': response['Item']["s3_key_input_file"]},
        ExpiresIn=300)
    except ClientError as e:
      logging.error(e)
    comp_time_epoch = response['Item']['complete_time']
    comp_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(comp_time_epoch))
    if curr_time_epoch - comp_time_epoch > app.config['FREE_USER_DATA_RETENTION']: free_expired = True

  profile = get_profile(identity_id=session.get('primary_identity'))
  role = profile.role
  if user_id == response['Item']['user_id']:
    return render_template('annotation.html',
                           annotation=response['Item'],
                           req_time=req_time,
                           input_presigned_url=input_presigned_url,
                           comp_time=comp_time,
                           result_presigned_url=result_presigned_url,
                           role=role,
                           free_expired=free_expired)
  else: abort(403)




"""Display the log file for an annotation job
"""
@app.route('/annotations/<id>/log', methods=['GET'])
@authenticated
def annotation_log(id):
  dynamodb = boto3.resource('dynamodb', region_name=app.config['AWS_REGION_NAME'])
  ann_table = dynamodb.Table(app.config['AWS_DYNAMODB_ANNOTATIONS_TABLE'])
  user_id = session['primary_identity']
  response = None
  try:
    response = ann_table.get_item(Key={'job_id': id})
  except ClientError as e:
    logging.error(e)

  s3 = boto3.resource('s3')
  obj = s3.Object(app.config['AWS_S3_RESULTS_BUCKET'], response['Item']['s3_key_log_file'])
  log = None
  # https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
  try:
    log = obj.get()['Body'].read().decode('utf-8')
  except ClientError as e:
    logging.error(e)

  if user_id == response['Item']['user_id']:
    return render_template('annotation_log.html', log=log)
  else: abort(403)


"""Subscription management handler
"""
import stripe

@app.route('/subscribe', methods=['GET'])
@authenticated
def subscribe_get():
  user_id = session.get('primary_identity')
  profile = get_profile(identity_id=user_id)
  if profile.role == 'premium_user': abort(403)
  return render_template('subscribe.html')

@app.route('/subscribe', methods=['POST'])
@authenticated
def subscribe_post():
  user_id = session.get('primary_identity')
  profile = get_profile(identity_id=user_id)
  if profile.role == 'premium_user': abort(403)

  stripe.api_key = app.config['STRIPE_SECRET_KEY']
  token = request.form['stripe_token']
  customer = None
  # https://stripe.com/docs/api/customers/create?lang=python
  try:
    customer = stripe.Customer.create(
      source=token,  # obtained with Stripe.js
      name=profile.name,
      email=profile.email
    )
  except Exception as e:
    abort(500)
  # https://stripe.com/docs/api/subscriptions/create
  try:
    subscription = stripe.Subscription.create(
      customer=customer['id'],
      items=[
        {
          "plan": "premium_plan",
        },
      ]
    )
  except Exception as e:
    abort(500)

  update_profile(
    identity_id=session['primary_identity'],
    role="premium_user")
  # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
  sns = boto3.resource('sns', region_name=app.config['AWS_REGION_NAME'])
  topic = sns.Topic(app.config['AWS_SNS_RESULTS_RESTORE_TOPIC'])

  data = {'user_id': user_id}

  try:
    topic.publish(
      TopicArn=app.config['AWS_SNS_RESULTS_RESTORE_TOPIC'],
      Message=json.dumps(data)
    )
  except ClientError as e:
    logging.error(e)
    abort(500)

  return render_template('subscribe_confirm.html', stripe_id=customer['id'])


"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Home page
"""
@app.route('/', methods=['GET'])
def home():
  # update_profile(
  #   identity_id=session['primary_identity'],
  #   role="premium_user")
  return render_template('home.html')

"""Login page; send user to Globus Auth
"""
@app.route('/login', methods=['GET'])
def login():
  app.logger.info('Login attempted from IP {0}'.format(request.remote_addr))
  # If user requested a specific page, save it to session for redirect after authentication
  if (request.args.get('next')):
    session['next'] = request.args.get('next')
  return redirect(url_for('authcallback'))

"""404 error handler
"""
@app.errorhandler(404)
def page_not_found(e):
  return render_template('error.html',
    title='Page not found', alert_level='warning',
    message="The page you tried to reach does not exist. Please check the URL and try again."), 404

"""403 error handler
"""
@app.errorhandler(403)
def forbidden(e):
  return render_template('error.html',
    title='Not authorized', alert_level='danger',
    message="You are not authorized to access this page. If you think you deserve to be granted access, please contact the supreme leader of the mutating genome revolutionary party."), 403

"""405 error handler
"""
@app.errorhandler(405)
def not_allowed(e):
  return render_template('error.html',
    title='Not allowed', alert_level='warning',
    message="You attempted an operation that's not allowed; get your act together, hacker!"), 405

"""500 error handler
"""
@app.errorhandler(500)
def internal_error(error):
  return render_template('error.html',
    title='Server error', alert_level='danger',
    message="The server encountered an error and could not process your request."), 500

### EOF