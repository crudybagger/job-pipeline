# Job Finder and application pipeline

This pipeline is responsible to scrape jobs on the web and filter out the relevant jobs based on candidates criterias.

On a High level, this pipeline consists of 4 stages.

## Stage 1 : Job Scraping and Filtering
This part of the pipeline scrapes different job boards governed by a simple config. The keywords to search for are also maintained in the config. 
This pipeline then alayses all the found jobs and thier job descriptions to find a match score for the candidate. The match score is calculated based on the existing experience of the candidate as well as the future prospects of the job and corellation with current ongoing Education.
After Analysis of all the factors, separate queues are maintained for passed and rejected jobs. The match score needs to be configurable and should be expected to be reconfigured based on a manual analysis of the rejected jobs list by a human.
The lists/queues should be stored in persistent storage and should have proper interactive tooling to accept the rejected jobs by the pipeline as well as to view the accepted jobs.
All the below data needs to be collected for each and evey job.
1. Title of the Job position
2. Job Description 
3. Company Name and website
4. Email/Other contact details of the Job poster

In addidtion certain metadata also needs to be appended to the entry in the list.
The Metadata contains of a 'base resume' which should be a pre configured path to a resume starting point for further stages of this pipeline. The metadata also contains miscellaneous notes section.

## Stage 2 : Matching Resume Generation
This stage of the pipeline solely focuses on generating bulletpoints, skills and summary for the candidate based on a job description. The stage analyses the base resume for skills and past experience and also analyses the job description to naturally work the keywords of the job description into the past experience and summary of the candidate.
This stage works on an existing resume in LaTeX and only edits minimal and required sections. The language should be very human for the resume.

In addition to the resume generation, this stage also needs an independent sub stage, that acts as an ATS for the given job. The substage takes in the job description and the generated resume and scores the resume based on the job description like a professional resume screener and Tech hiring manager for the job. This substage also provides feedback as notes to improve the resume by highlighting missing keywords or misaglined points in the resume.
The substage then adds the notes back to the job and resume entry and stage 2 should pick it back up. This loop should run as much as required, reiterating on the resume.
If the substage marks the entry as ready, it is then picked up by the next stage. The entry here should be stored in a different queue than before for clarity. 

## Stage 3 : Matching Cover Letter Generation
This stage picks the entries that have a resume with good score generated in the previous stage and generates matching cover letter for the application to this job with the generated resume.
This stage goes in and alayses the company posting the job, the department of the job, the hiring manager and any social information present on the internet about the job, department, hiring manager, etc.
Post collecting this information about the company, this stage analyses the context about the candidate analyses the strong points and story building hooks from the resume and the overall experience of the candidate. There are addidtional resources and context configured for this stage that help it build a good story, defined in the config.
The cover letter should be consistent across various runs of this stage on various jobs. It should follow repeatable pattern like follows.

Story Hook -> Candidate Background -> Candidate Experience -> Candidate Skills -> Candidate Story -> Candidate Fitment for the job -> Candidate Interest in the job and company -> Candidate Closing Statement.


The cover letter should be human and should not sound like a generic cover letter. It should be specific to the job and the company. The cover letter should be in a format that is acceptable to the company and should be in a format that is acceptable to the job board.

## Stage 4 : Compilation of job link, description, resume and cover letter into a single text message

This stage takes the job link, job description, generated resume and generated cover letter and compiles them into a single text message that can be sent to the candidate for review and easy application to the job. This stage also would need external integration with a messaging platform like WhatsApp, Telegram, Signal, etc. to send the message to the candidate.
Any job which is sent to the candidate should be marked as sent and stored in a separate queue for tracking and future reference. This stage should also have a simple interface to view the sent jobs and the status of the sent jobs. The candidate should be able to mark the job as applied or not applied and should be able to provide notes about the job and the resume and cover letter. This notes should be stored in the job entry metadata for future reference and analysis.