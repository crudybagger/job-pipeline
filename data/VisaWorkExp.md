Organizational Overview
The Data and AI Organization of which I was a part was concerned with everything Data and AI
in Visa.
My Business Unit specifically worked on the Risk Evaluation Platform which included various AI
models as our product used for assessing the risk of a given transaction.
Every transaction is scored on different scales by different models and finally assigned a risk
score based on which various clients can decide whether to approve or decline the transaction.
The models themselves were of various kinds, some legacy decision tree based models as well
as new initiatives based on the transformer architecture, Primarily managed by the Data
Science team. We worked on the entire end to end platform that hosted these models, an AI
Inferencing Engine. The Platform itself had different people working on various layers, We had
Data Aggregation services built in Rust that pulled the required features for the model and made
it ready for the model in Redis.
A Go service acted as the entrypoint and the router which finally routed the inference request to
one or more models.
Over My Tenure a key focus was on the scalability, availability and success rate metrics for the
platform and various new initiatives were taken for each of these metrics.
TSS
The first product that my team of 4 people (1 Manager and 3 Engineers) managed was called
TSS (Transaction Simulation Service) which was aimed at measuring and improving the
scalability of the platform.
This tool replicated real production traffic in a pre production environment with much higher
throughput to validate the scalability of the platform. Over my tenure we scaled the tool to
produce 100k Transactions per second over the previously 30k TPS it produced before without
increasing the underlying hardware.
This is a goLang service using the GoFlow library. It is hosted in a kubernetes cluster with over
40 replicas. A docker container built the golang application in a Rhel8 base image. A Jenkins
CICD pipeline was responsible for building the docker image, handling the helm chart
generation for each of the environments using the configuration stored in code and then
uploading to a jfrog artifactory which would be picked and deployed on the cluster.
These improvements were incremental and compounded with each update.
The tool itself was designed as a goflow graph with multiple concurrent services.
Some major improvements were correcting the order of operations on the data, some of the
steps were filtering out the transactions based on certain fields and another was a data mapping
of various fields and another was decryption of the PII data. By moving the filtering step before
the decryption ( we also needed to filter after the decryption if the filter was defined on any of
the PII data) we saw some improvement in the throughput.
Another Major jump in throughput in the tool came from not updating the tool itself but changing
the data source of the tool. Initially the tool read from a common source of truth kafka stream
with over 2000 features in the schema, it took a long time to parse as well as decode. Since the
actual freshness of the data did not matter during this phase for the tool, we pivoted and started
using another stream which had the same transactions but lot less fields, this stream was used
by the data science team to build the features of the same models we were testing so all of the
fields required for the specific models were already present in this stream. This was much light
weight and only included the necessary features (arround 200) this 10 fold reduction in the
payload size gave us a massive boost in the throughput.
Final Major update which I lead was emitting out proper telemetry and metrics about the
throughput at each stage of the go flow graph. The solution I designed was simple and very low
overhead. Each of the stages are connected with a small buffer and a metrics server started
publishing the count of transactions processed by each stage to a particular port for an opera
scraper to scrape the metrics. After analysing these number we fine tuned the number of
concurrent replicas of each of the go flow stage to maximise the throughput, the goal of this
exercise was to identify the bottleneck and tune the service so that the final inference is the
bottleneck. This would depict the true capacity of the inference engine rather than that of just
the tool. Although this also proved to be slightly challenging because of the network bottlenecks
between the tool and the inference engine server, But it was finally decided that the capacity
measured by the tool was to be focused on based on the argument that majority of our clients
would also have to pass through the same network infrastructure (load balancer)
Chaos Engineering
Amidst the improvements on the tool to get an accurate estimation of the scale capacity of our
inference system, I was tasked with taking on a new initiative of chaos testing our entire system
to improve the availability. During this time we maintained an already high 5 9's (99.999 %)
availability, our goal was to move towards 6 9's (99.9999%).
To do this I started by mapping out the entire journey of a transaction from the client itself and
the response back to the client. I mapped it via various services and teams and finally the actual
physical hardware to and from which each and every bit was getting transmitted.
This systemic mapping created an invaluable starting point for our research into the system.
After the mapping was complete I ran it via each and every team that was involved in the
journey and also our chief architect, it revealed lots of hard coded paths for various models
which were appropriately flagged, so we had already made some impact before we even began.
After we had an overall idea of the journey me and a senior engineer started out weighting
alternatives for the tools that we could use to identify failure points and injecting failures to
various systems.Since most of our stack was on our own VMs and many of the services were
just various processes running on the same machine, we decided to go with ChaosMesh as our
tool, I quickly started designing a system to inflict failures programmatically on our systems. The
design was following standard adapter pattern with a service that exposed standardized APIs
for low level functions tightly integrated with chaosMesh. On top of this service we built another
service which accepted as a yaml or json a list of scenarios and handled inflicting multiple
scenarios provided by chaosmesh in various sequences as well as running periodically and on
demand.
Chaos-Mesh Deamon which was installed on the physical nodes was a golang service and a
standard nomad job which managed the VM and the services also handled installation of this
demon onto each of the VM. A Jenkins pipeline was written to trigger each of the testcases.
The Jenkins Pipeline had the cron schedule with a given json config with a list of testcases to
trigger. I wrote this scheduler pipeline to manage the recovery of the system after each of the
test cases.
The most non trivial part of this project was designing the test cases, a test case needed to
have an hypothesis attached with a scenario of what to be expected from the entire system in
case of a specific failure in a specific service or multiple services. We started out with designing
the cases that targeted failures in specific services with standard failures for each of them. We
tested automatic recovery for each of the service, weather or not we had proper alerts firing on
each of the service failure, network partition between services and startup failures. On the VM
level we tested high CPU, memory and network bandwidth utilization as well as unreliable
communication between VMs. Each of these test cases revealed missing alerts high or
sometimes infinite MTTR and MTTD. Each of them slowly got fixed by the respective teams.
Then we moved to more complex scenarios and multiple instance failures and then to multiple
service failures. These exercises improved our documentation as well as the Standard
operating procedure for DevOps and SRE teams in case of failures.
This initiative also proved extremely useful during new major feature releases and they were
correctly stopped before reaching production when they failed any of the reliability chaos tests.
We realised that the majority of the availability misses and success rate misses came from
Redis as a dependency. The redis downtime during patching and maintenance hurt our overall
system availability. To counter this we divided each of our DCs into two independent stacks with
independent kafka and redis instances as well as new load balancers, each of them providing
more durability and could be taken down for maintenance individually. A new system was built
that monitored the health of each of the stacks and managed the routing rule for the traffic to
either of the stacks.
To improve latency and success rate a new feature called request hedging was introduced. We
observed that p99 latencies were breaching our SLA while p90 was well within half of our
latency budget. This naturally lead to the idea that we could wait for p50 latency amount of time
and if we did not receive a response back, we could fire another request to the other stack
which would more often than not still be faster than p99 on the first stack. This proved to be
correct and we saw reduction in our overall p99 latency as well as reached our Success rate
goal of 99.999% consistently for the past 2 Quarters.
Chaos testing these new systems helped iron out bugs in edge cases very early on and
accelerated the progress as well. It also acted as a testing ground to prove that the feature
actually raised reliability of the system