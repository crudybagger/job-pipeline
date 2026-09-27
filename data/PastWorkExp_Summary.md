I am Sarang, an enthusiastic Software Engineer, currently working at Amazon, in the UPI
payments team. I graduated from NIT Warangal in 2023, after which I joined Raze as a backend
developer for a contractual role. Raze is a B2B SaaS startup where we were building the
product from ground up and Raze was in the process of 0->1, I joined Amazon in January last
year where I have contributed to various features and systems, primarily backend, but also built
out few pages in Amazon App, since we are in the process of migrating from older tech to
ReactJS for out frontend. At Amazon I have used AWS extensively to build out system
architecture and solve business needs
1. Stress Testing
At Amazon when I was an SDE Intern, my team wanted to test the resilience of our services and
measure the breaking point under high load.
I was given the task to utilize the internal stress testing library at amazon and build out a service
to do this. I used Java to build a backend service that generated mock requests to our service
and kept varying the load exponentially to measure when our core service would start failing.
This had never been done before in my team, and faced with Ambiguity and no senior with the
exact knowledge in the team, I had to read multiple internal documents and learn the nuances
of the stress testing library we had.
During this I faced a major hurdle: the backend service I wrote was unable to generate enough
load to test our core service, since it was running on a ec2 instance which was much smaller
than the one our service was running on. I had to escalate and influence my managers for a
larger ec2 instance quickly, since my internship was of fixed duration and bound to end soon. It
took some time but I was able to get the larger instance allocated and got the resilience metric
measured, which hadn't been measured before, just a day before my internship ended.
I learned what went behind keeping the servers running and how to prepare our services for
high throughput scenarios.
- Retry Enhancement
- SSE Migration API
2. Reducing Onboarding Clicks for Amazon Customers
The customer bank onboarding process is a critical step in any UPI service, at Amazon pay, we
observed that most number of customer drop offs were happening during this stage, specifically
on the page where customers have to select a bank, and a solution was needed to reduce the
drop offs, My team came up with innovative solution of skipping the page altogether and making
the bank selection for customers ourselves.
I collaborated on redesigning the architecture, and implementing the solution of predicting
customer banks without them selecting it themselves, making the customer onboarding simpler
and reducing the number of clicks any customer has to make while registration, I built out new
APIs along with my teammates. Using AWS components like Lambda and DynamoDB, we
designed the architecture of the system and go upwards of 70% success of prediction of banks.
Onboarding clicks were halved, this also lead to an 8% improvement in overall issuance
success rate since there were less dropoffs during the registration journey. the end to end
registration latency also dropped significantly, since customers didn't have to select a bank
themselves. I realized that a user-centric approach combined with use of data and metrics to
identify the pain points, can allow us to create the highest impact.
3. Improving Payment Success Rates
NPCI has a huge impact on what we do and what projects we take up, since it is the governing
body running UPI ecosystem in india. We also have payment service providers that connect us
with the banks to make transactions. Initially NPCI was strict on customers being registered on
only a single payment service provider and that's what we did, but due to every service provider
having different transaction rates, we onboarded a large portion of our customer base on that
particular service provider. This also created a single point of failure, if the service provider went
down. despite us having multiple service providers, our customers are unable to transact using
UPI, after lots of back and forth, NPCI allowed everyone to use multiple service providers for a
single customer, that's why in 2024 you must have seen multiple VPA handles, @ybl @axl and
so on on the same app.
The teammate that was doing the work of building a system to register the existing customers
on multiple service providers was about to leave the team, so I took the initiative and asked my
manager to give the ownership of the task, the architecture was already designed so I had to
implement a few bits and pieces like sending out a notification to customers giving them an
option to opt out of the process. After building that I started running the process, I had to
carefully run it since it was adding the customers like a first time registration in the UPI
ecosystem, I couldn't run it above a certain speed, and the process took months to complete,
but now Amazon pay is much more resilient and it also increased the payment success rates
since banks being down is a common scenario.
4.Building a Server-to-Server Communication System (Raze)
At Raze, A Microservice architecture was already built by the founder, and I was initially tasked
with building a notification system for the customers via email. I built out a service to send out
notifications and put it in front of a RabbitMQ server to handle the load gracefully. I also
integrated it with various flows, like welcome mail post registration, forgot password mail for
login and also built an internal endpoint for marketing mails.
Looking at the architecture I realised that the RabbitMQ server I build, could be utilised between
the microservices to handle the server-to-server communication and build asynchronous flows,
currently only synchronous communication was happening between the services. So I took the
initiative and extended the design to handle serer-to-server communication as well. making the
system more responsive, I also built out a worker service where one could build out worker
functions and consume the messages from the queue.
This resulted in improved efficiency, enabling smoother communication between services.
I deepened my understanding of microservices architecture and the importance of designing for
scalability from the ground up by building this.
4. Leading Ticketing System Development (Spring Spree)
As the Lead Software Developer for Spring Spree, in my final year at NIT Warangal, I needed to
develop a ticketing and payment system to handle a high volume of transactions during the
event. The goal was to design a reliable system capable of managing high expected footfall of
attendees seamlessly.
I took interviews of juniors and gathered an enthusiastic team for backend development. I led
the team of developers to build subsystems for ticketing and payment using ReactJS, Node.js,
and MongoDB. I built out the integration with Razorpay for seamless payments. I also mentored
juniors, ensuring timely delivery and high-quality work. I was responsible for distributing work as
required, which came from the requirements itself, or sometimes from other student teams
managing springspree, for example the marketing team wanted a profile picture generator,
which would spit out a profile picture with the spring spree border.
The system handled the event's high traffic flawlessly, enhancing the user experience and
contributing to the event’s success. I learned the importance of team management, breaking
down complex projects, and delivering under tight deadlines.