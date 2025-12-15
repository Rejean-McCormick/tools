
# 22\. Claim Check Pattern

## 1\. The Concept

The Claim Check pattern is a messaging strategy used to handle large message payloads without overloading the message bus. Instead of sending the entire dataset (the "luggage") through the message queue, you store the payload in an external data store (the "cloakroom") and only send a reference pointer (the "claim check") via the queue. The receiver uses this reference to retrieve the full payload later.

## 2\. The Problem

  * **Scenario:** An Insurance Processing System. Users upload photos of car accidents (High Resolution, 10MB each) and a massive JSON report.
  * **The Constraint:** Most message brokers have strict limits on message size to ensure low latency and high throughput.
      * **AWS SQS:** Max 256 KB.
      * **Kafka:** Defaults to 1 MB (can be increased, but performance degrades).
      * **RabbitMQ:** technically supports larger messages, but sending 50MB blobs will clog the network and crash consumers.
  * **The Failure:** If you try to verify the car accident photo by shoving the Base64 encoded image directly into the Kafka topic, the producer throws a `MessageTooLargeException`. Even if it succeeds, your brokers choke on the bandwidth.

## 3\. The Solution

Split the transmission into two channels:

1.  **The Data Channel (High Bandwidth):** Upload the heavy payload to a Blob Store (S3, Azure Blob, Google Cloud Storage).
2.  **The Control Channel (Low Latency):** Send a tiny JSON message to the broker containing the location (URI) of the blob.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "The message is too big for Kafka? I'll just edit the `server.properties` and increase `max.message.bytes` to 50MB." | **System Degradation.** The Kafka brokers run out of RAM and disk I/O. The entire cluster slows down for everyone, not just this topic. |
| **Senior** | "Upload the file to S3 first. Send the S3 Key in the message. The consumer will download it only if and when it needs to process it." | **Efficiency.** The broker remains fast and lightweight. The heavy lifting is offloaded to S3, which is designed for large objects. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Large Payloads:** Images, PDFs, Video files, Audio logs.
      * **Massive Datasets:** A generated report with 100,000 rows of SQL data.
      * **Cost Optimization:** Storing 1TB of data in Kafka/SQS is expensive. Storing it in S3 is cheap.
  * ❌ **Avoid when:**
      * **Small Messages:** If the payload is 5KB, uploading to S3 adds unnecessary latency and complexity. Just send it.
      * **Ultra-Low Latency:** The extra HTTP round-trip to S3 (Upload + Download) adds 50-200ms. If you are doing High-Frequency Trading, this is too slow.

## 6\. Implementation Example (Pseudo-code)

**Scenario:** Processing a user-uploaded PDF invoice.

### The Producer (Sender)

```python
import boto3
import json

s3 = boto3.client('s3')
sqs = boto3.client('sqs')

def send_invoice_for_processing(user_id, pdf_bytes):
    # 1. Store the Payload (The Luggage)
    object_key = f"invoices/{user_id}/{uuid.uuid4()}.pdf"
    
    s3.put_object(
        Bucket='my-heavy-payloads',
        Key=object_key,
        Body=pdf_bytes
    )
    
    # 2. Create the Claim Check (The Ticket)
    message_payload = {
        "type": "InvoiceUploaded",
        "user_id": user_id,
        "claim_check_url": f"s3://my-heavy-payloads/{object_key}",
        "timestamp": time.time()
    }
    
    # 3. Send the Check via Broker (Tiny message)
    sqs.send_message(
        QueueUrl='https://sqs.us-east-1.../invoice-queue',
        MessageBody=json.dumps(message_payload)
    )
```

### The Consumer (Receiver)

```python
def process_queue_message(message):
    data = json.loads(message.body)
    
    # 1. Inspect the Claim Check
    s3_url = data['claim_check_url']
    
    # 2. Retrieve the Payload (Walk to the cloakroom)
    # Only download if we actually need the file now
    bucket, key = parse_s3_url(s3_url)
    
    response = s3.get_object(Bucket=bucket, Key=key)
    pdf_content = response['Body'].read()
    
    # 3. Process Logic
    extract_text_from_pdf(pdf_content)
    
    # 4. Optional: Clean up the Blob?
    # Depends on retention policy.
```

## 7\. Garbage Collection Strategy

One risk of the Claim Check pattern is **Orphaned Data**.

  * If the message is processed and deleted from the queue, the blob remains in S3.
  * Over time, you might accumulate terabytes of useless data.

**Solutions:**

1.  **Consumer Deletion:** The consumer deletes the S3 blob immediately after processing. (Risk: If processing fails mid-way, you lose the data).
2.  **TTL (Time To Live):** Configure an S3 Lifecycle Policy to automatically delete objects in the temporary bucket after 7 days. This is the robust, "set and forget" Senior approach.

## 8\. Smart Claim Check (Hybrid)

Sometimes you need *some* data to make a routing decision (e.g., "Is this a VIP user?").

  * **Strategy:** Include critical metadata (User ID, Type, Priority) in the message header/body, but keep the heavy binary data in the Claim Check.
  * This allows Consumers to filter or route messages *without* downloading the 50MB file.