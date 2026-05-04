# Guided tour through CCR's JATSmith setup

CCR uses JATSmith hosted at [proofs.computationalcommunication.org/](https://proofs.computationalcommunication.org/). Since this requires a login, 
here are some screenshots that show how JATSmith is used in practice

<img width="1625" height="871" alt="image" src="https://github.com/user-attachments/assets/0257ccc4-2c10-4ab4-942e-d692cddeb50e" />

# (1) Editor initiates workflow

After logging in, the editor sees an overview of manuscripts in the pipeline, and has a button to add a new manuscript.
This connects to OJS (open journal systems) to retrieve an overview of manuscripts in the copy-editing stage that have 
a DOI assigned and are not yet imported into JATSmith:

<img width="1654" height="1116" alt="image" src="https://github.com/user-attachments/assets/226a320f-a45f-407d-954c-a836c5f73c5b" />

(Note that I purposefully selected articles here that are already published to avoid privacy / confidentiality issues.)

# (2) Editor invites authors

After importing the manuscript, the metadata is automatically extracted from OJS, including publication details such as DOI, issue, and acceptance date:

<img width="1621" height="1066" alt="image" src="https://github.com/user-attachments/assets/6cb94167-d0d6-42eb-bfde-ad51738459d3" />

At the bottom of the article details card, editors can copy a pre-signed link which includes a token that allows authors access to a single manuscript.
It also gives the option to invite the authors by email, which sends a brief (editable) explanation to the author as well as the link (masked in the screenshot):

<img width="1632" height="1532" alt="image" src="https://github.com/user-attachments/assets/3549b47c-576c-4c29-a19e-785e87a185ad" />

# (3) Author uploads source

Upon receiving the link, the author can access the manuscript page:

<img width="1645" height="1226" alt="image" src="https://github.com/user-attachments/assets/fe80c679-1bae-44e0-9bce-90a5539ce7a9" />

(Note: using the optional light mode here to make the distinction between author and editor clear)

They can then upload the manuscript files directly, or link to a public or private git source (including overleaf)

<img width="1394" height="690" alt="image" src="https://github.com/user-attachments/assets/0731a8c1-5147-4d54-9939-cac7337a876e" />

# (4) Author runs conversion 

After uploading the manuscript source (latex or quarto), the author can start the conversion process. 
This includes options for applying some minor fixes to common latex problems which trip up the XML conversion,
and a option to automatically inject the most up to date class or quarto extension files. 

This will automatically compile the PDF, run `latexml`, apply the various fixes, check the metadat, and validate the resulting XML against the JATS Schema.
Since conversion can take fairly long (up to 10 minutes), the user is asked whether they want to receive an email when the process finishes:

# (5) Author checks warnings and approves the proofs

After conversion is done, the author can see any issues discovered during conversion:

<img width="1970" height="1570" alt="image" src="https://github.com/user-attachments/assets/383906b9-989f-488d-9ddd-bbd650b6c4f5" />

In this case, the prepration step flagged a problem with line breaks within a multirow table cell, with a suggestion to wrap the content in the source.
The metadata check flagged a discrepancy between the abstract in OJS (entered on first submission) and the current abstract from the source,
and offers an action to replace the current value in OJS with the abstract from the manuscript. 

In addition, the author can check the PDF, XML, and HTML proofs. The PDF is the direct result of the latex/quarto render stage. 
The XML is the JATS-XML created by the `latexml` process and fixes. The HTML proofs are created directly from the XML using an XSLT stylesheet,
so it functions as a user-friendly way to check the XML correctness. We opted to use a style sheet that is close to our PDF,
but it you have direct access to the style sheet that will be used for final publication that would be even better

<img width="1972" height="1651" alt="image" src="https://github.com/user-attachments/assets/31518271-4b91-4c75-b4ff-19a5932d2ab7" />

If the author is satisfied with the proofs (and sees no problematic warnings in the pipeline output), they can approve the proofs:

<img width="1459" height="1032" alt="image" src="https://github.com/user-attachments/assets/7030d783-dd59-44cd-8eb1-40d0765726a4" />

This freezes the manuscript into 'approved' stage, after which the editor can publish the manuscript

# (6) Editor downloads the publisher files and source archive

After the author approves the proofs, the editor can do a final check (if desired) and un-approve the manuscript and notify the author if more changes are needed.

<img width="2009" height="1206" alt="image" src="https://github.com/user-attachments/assets/ad1f829a-d99d-4a52-a61e-9721ec9bfe13" />

If the editor is satisfied, they can download the *publisher zip* (containing the PDF, XML, and any images) for production, 
and the *source  archive* for archival (in case it is later needed to e.g. re-convert manuscripts)

(Note: we plan to add a feature to automatically re-upload these results to OJS in the future -- stay tuned!)

# Site settings and branding

The screenshots above are all from the CCR's JATSmith instance. 
You can easily spin up a local version for testing. 

Since journal metadata (ISSN etc) are automatically injected into the latex or quarto sources, these need to be configured in the 'site config' screen.
This also allows the editor to set branding information as well as linking to the latest version of the latex class file or quarto extension:

<img width="1336" height="1987" alt="image" src="https://github.com/user-attachments/assets/dba2967b-fd2d-45ec-ad30-70d266c4f17b" />

The more sensitive settings, such as editor credentials, OJS integration and email details are set in the [.env](deply/.env.example) file.

For example, here is the (masked) `.env` file used for CCR:

```
wva@CCR-JATSmith:~$ cat .env 
# Domain name for the web service (Caddy handles TLS automatically)
SITE_ADDRESS=proofs.computationalcommunication.org

# Image version (set to a specific release tag, or "latest")
VERSION=latest

# Optional: override default ports
# HTTP_PORT=80
# HTTPS_PORT=443

EDITOR_CREDENTIALS=****

OJS_ADMIN_TOKEN=****
OJS_BASE_URL=https://journal.computationalcommunication.org
OJS_JOURNAL_PATH=ccr

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=****@gmail.com
SMTP_PASSWORD=****
SMTP_FROM=****@gmail.com
```



