# Genomics Annotation Service

## 2 Bonus 
Use 150KB as the input file size limit for Free users. This aligns with the five sample input VCF files provided (the two free files are both below this limit). When a Free user tries to upload a larger file, display a message and prompt them to subscribe. Include a note (in your README.md) describing how you implemented this check.

I used client-side validation. I disabled the submit button by default. Once the user selects the file, if the user is a free user, the script checks the size of the file mounted for upload. If it is greater than 150KB, a message is displayed to upload to premium and the submit button remains disabled, if less than 150KB, the submit button is enabled. If the user is a premium user, the submit button is enabled with the selection of any size file.

## 7 Archive Free User Data to Glacier using message queue
The message queue design was chosen for its high durability, availability guarantees, load visibility, and architectural flexibility. Message queues allow application responsiveness by persisting long running tasks and decoupling the application from the task processors. An SNS notification service is also used with the SQS to allow a robust scalable pub-sub configuration. Instead of having the application figure out which queues the task should be sent to, the application publishes a message to the appropriate topic and then the SNS sends out notification messages to all the queues that have subscribed to it. This allows for greater independent scalability and durability. 

In our case, after a job completes, a message is sent to archive the job via SNS to a SQS queue. The queue has the "DelaySeconds" attribute set to 10 minutes in order to give the user time to download the results file before it becomes archived. SQS has the benefit of guaranteed availability and delivery. If an instance fails to process the delete request, the queue will be able retain the message and allow another instance to process the delete request at a later time. A standard queue was used as the ordering was not all that important as long as the result file was archived at approximately 10 minutes. Long polling was also used because we did not expect very high demand initially and using standard polling would result in frequent wasteful empty polls. 

## 9 Restore data for users that upgrade to Premium
Once a user upgrades to a premium subscription plan, a message is sent to the the job restore SNS topic with the job id and user_id and subsequently enters another SQS queue. The results_restore.py utility instance polls from this queue, queries DynamoDb to obtain all the jobs associated with this user and initiates the restore job. Once the restore job is finished, a message is automatically sent to SNS, which in turn sends a message to the "thaw queue". Again, the SNS and message queue design allows for better failure tolerance and independent scaling because the two operations are decoupled. Since there is an intemittent delay between restore and thaw operations, it also makes sense to have two separate queues. Once in the queue, the "results_thaw.py" utility instance picks up the message and downloads the restored job. 

## 13(d) 
Monitor your auto scaling group and note when instances are added. Briefly describe what you observe, and explain why you think instances launch (or not) when they do.

With 300 users set up to make get requests to the GAS service at 1-3 second intervals, the overall load ramped up to approximately 150 requests per second. This is well above the scale out policy alarm threshold that was set at 200 requests per 60 seconds. Since the alarm was set off with one data point over the threshold, the auto scaling group incrementally added instances until the max limit was reached. Since the "cool-off" period was set to 300 seconds, the auto scaling group waited this much time before increasing the number of instances again even though the alarm was constantly being triggered. 

## 13(e)
After observing scale out behavior, stop your test by hitting the red STOP button on the Locust web console. Monitor your auto scaling group and briefly describe what happens when your scale in policy goes into effect.

Once the STOP button is hit, the load begins to drop and the response time begins to drop as a result. After a while, the response time drops below an average 10 ms per 60 seconds, which is the policy's scale-in alarm threshold. Consequently, the auto-scaling policy begins to remove instances one by one until it reaches the minimum specified. Just like in the scale-out case, the policy waits 300 seconds before allowing another scaling activity. 

## 14
To test the annotator scaling policies, I wrote the "ann_load.py" script to send a message to sns and the "job_requests" queue every 10 seconds. This should have been enough to satisfy the scale-out policy alarm (NumberOfMessagesSent > 10 for 1 datapoints within 5 minutes) for the annotators. However, since events take effect in different services independently, there was a significant time lag between the messages sent and then them showing up later in the CloudWatch metrics. There also seemed to be somewhat lack of synchronization of sampling periods between CloudWatch and SQS perhaps due to differences in resolution. Some samples would show approximately the expected amount of messages sent to the queue, while some samples would drop back down abruptly to zero, even though the messages were still constantly being sent. Due to these reasons, the scaling did not occur continously to the maximum amount of 10. Instead, since the scale-in alarm (NumberOfMessagesSent < 5 for 2 datapoints within 2 minutes) was also being triggered, the number of instances would fluctuate between 2 and 4. In order to get more predictable scaling behavior, adjusting the sampling resolution and periods would be helpful as well as waiting for the two decoupled systems to reach steady state before conducting the testing. 

## References
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.put_item
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.update_item
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#topic
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
https://stripe.com/docs/api/customers/create?lang=python
https://stripe.com/docs/api/subscriptions/create
https://stackoverflow.com/questions/41827963/track-download-progress-of-s3-file-using-boto3-and-callbacks
https://docs.python.org/3/library/subprocess.html
https://stackoverflow.com/questions/793858/how-to-mkdir-only-if-a-dir-does-not-already-exist
https://medium.com/@ageitgey/python-3-quick-tip-the-easy-way-to-deal-with-file-paths-on-windows-mac-and-linux-11a072b58d5f
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-example-download-file.html
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html#queue
https://docs.google.com/document/d/1JNXr4FE8WKAsO6oI0HBtmwNQ7u__J45feOwnb7d1qjM/edit
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html
https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStarted.Python.03.html#GettingStarted.Python.03.03
https://stackoverflow.com/questions/1601455/how-to-check-file-input-size-with-jquery
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/sqs.html
https://stackoverflow.com/questions/31976273/open-s3-object-as-a-string-with-boto3
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.upload_archive
https://docs.aws.amazon.com/ses/latest/DeveloperGuide/send-using-sdk-python.html
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html#DynamoDB.Table.query
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.initiate_job
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.get_job_output
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier.html#Glacier.Client.delete_archive

## Extra Notes for Grader
Files changed in web/templates:
annotate.html
annotation.html
annotations.html
subscribe_confirm.html


