

# 25\. Immutable Infrastructure

## 1\. The Concept

Immutable Infrastructure is an approach where servers are never modified after they are deployed. If you need to update an application, fix a bug, or apply a security patch, you do not SSH into the server to run `apt-get update`. Instead, you build a completely new machine image (or container), deploy the new instance, and destroy the old one.

## 2\. The Problem

  * **Scenario:** You have 20 servers running your application. They were all set up 2 years ago.
  * **The Configuration Drift:** Over time, sysadmins have logged in to tweak settings:
      * Server 1 has `Java 8u101` and a hotfix for Log4j.
      * Server 2 has `Java 8u102` but is missing the hotfix.
      * Server 3 has a random cron job installed by an employee who quit last year.
  * **The "Snowflake" Server:** Each server is unique (a snowflake). If Server 5 crashes, nobody knows exactly how to recreate it because the manual changes weren't documented.
  * **The Fear:** "Don't touch Server 1\! If you reboot it, it might not come back up."

## 3\. The Solution

Treat servers like cattle, not pets.

1.  **Bake:** Define your server configuration in code (Dockerfile, Packer). Build an image (AMI / Docker Image). This image is now "frozen" and immutable.
2.  **Deploy:** Launch 20 instances of this exact image.
3.  **Update:** To change a configuration, update the code, bake a *new* image (v2), and replace the old instances.
4.  **Prohibit SSH:** In extreme implementations, SSH access is disabled. No human *can* change the live server.

### Junior vs. Senior View

| Perspective | Approach | Outcome |
| :--- | :--- | :--- |
| **Junior** | "I'll use Ansible to loop through all 100 servers and update the config file in place." | **Drift & Decay.** If the script fails on server \#42, that server is now inconsistent. The state of the fleet is unknown. |
| **Senior** | "I'll build a new Docker image with the new config. Kubernetes will roll out the new pods and terminate the old ones." | **Consistency.** We know exactly what is running in production because it is binary-identical to what we tested in staging. |

## 4\. Visual Diagram

## 5\. When to Use It (and When NOT to)

  * ✅ **Use when:**
      * **Cloud / Virtualization:** It requires the ability to provision and destroy VMs/Containers instantly (AWS, Azure, Kubernetes).
      * **Scaling:** Auto-scaling groups need a "Golden Image" to launch new instances from automatically.
      * **Compliance:** You can prove to auditors exactly what software version was running at any point in time by showing the image hash.
  * ❌ **Avoid when:**
      * **Physical Hardware:** You cannot throw away a physical Dell server every time you update Nginx. (Though you can re-image it via PXE boot, it's slow).
      * **Stateful Databases:** You generally *do* patch database servers in place (or rely on managed services like RDS) because moving terabytes of data to a new instance takes too long.

## 6\. Implementation Example (Packer & Terraform)

### Step 1: Define the Image (Packer)

Create a definition that builds the OS + App dependencies.

```json
{
  "builders": [{
    "type": "amazon-ebs",
    "ami_name": "my-app-v1.0-{{timestamp}}",
    "instance_type": "t2.micro",
    "source_ami": "ami-12345678"
  }],
  "provisioners": [{
    "type": "shell",
    "inline": [
      "sudo apt-get update",
      "sudo apt-get install -y nginx",
      "sudo cp /tmp/my-app.conf /etc/nginx/nginx.conf"
    ]
  }]
}
```

*Run `packer build` -\> Output: `ami-0abc123`*

### Step 2: Deploy the Image (Terraform)

Update your infrastructure code to use the new AMI ID.

```hcl
resource "aws_launch_configuration" "app_conf" {
  image_id      = "ami-0abc123" # The new immutable image
  instance_type = "t2.micro"
}

resource "aws_autoscaling_group" "app_asg" {
  launch_configuration = aws_launch_configuration.app_conf.name
  min_size = 3
  max_size = 10
  
  # Terraform will gradually replace old instances with new ones
}
```

## 7\. The Golden Image vs. Base Image

  * **Golden Image:** Includes the OS, dependencies, AND the application code.
      * *Pros:* Fastest startup (machine is ready to serve traffic immediately).
      * *Cons:* Slow build time (every code change requires baking a full VM image).
  * **Base Image (Hybrid):** Includes OS + Dependencies (Java/Node). The Application code is downloaded at boot time (User Data).
      * *Pros:* Faster CI/CD pipeline.
      * *Cons:* Slower startup/scaling time.
      * *Senior Choice:* Use **Docker**. The "Golden Image" build time for a container is seconds, giving you the best of both worlds.

## 8\. Troubleshooting (The "Debug Container" Pattern)

If you can't SSH into production, how do you debug a crash?

1.  **Centralized Logging:** Logs must be shipped to ELK/Splunk immediately. You debug via logs, not `tail -f`.
2.  **Metrics:** Prometheus/Datadog provides the health vitals.
3.  **The Sidecar:** In Kubernetes, you can attach a temporary "Debug Container" (with curl, netstat, etc.) to the crashing pod to inspect it without modifying the pod itself.

## 9\. Key Benefits Summary

1.  **Predictability:** Works in Prod exactly like it worked in Dev.
2.  **Security:** If a hacker compromises a server, you don't "clean" it. You kill it. The persistence of the malware is limited to the life of that instance.
3.  **Rollback:** Switch the Auto Scaling Group back to the previous AMI ID. Done.

