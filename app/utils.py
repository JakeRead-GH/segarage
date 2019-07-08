from flask_mail import Message
from app import app, mail
from werkzeug.utils import secure_filename
from wtforms import ValidationError
from time import time

import jwt
import os
import re

ALLOWED_EXTENSIONS_FILES = set(['txt', 'pdf', 'md', 'zip', 'tar', 'gz', 'docx', 'xlsx'])
FILETYPE_CHOICES = ['Binary', 'Scripts (Source code)', 'Readme', 'Other']

CATEGORY_LIST = set(['Mutation testing', 'Model-driven development', 'SPLs and OO repair', 'Test automation and failure diagnosis', 'Testing vulnerability', 'Testing', 'Program Understanding', 'Energy and requirement analysis', 'Analysis and refactoring', 'Verification and validation', 'Demonstrations Assistance', 'Authoring and Synthesis', 'Automated Programming Support', 'Empirical studies of code', 'Software evolution and maintenance', 'Software repair', 'Apps and App Stores', 'Search-based software engineering ', 'Program reduction technologies', 'Test improvement', 'Software comprehension', 'Human and social aspects of computing', 'Models and modeling', 'Inference and invariants', 'Test generation', 'Mining software repositories', 'Documentation', 'Development tools and frameworks', 'Recommendation systems', 'Formal methods', 'Web applications', 'Defect prediction', 'Debugging', 'Code smells', 'Concurrency', 'Product lines', 'Compilers', 'Emerging trends', 'Open source', 'Performance', 'Android', 'Repair and model synthesis', 'Specification and Verification', 'Patching and Fixing ', 'Tools and Environments', 'Research Testing ', 'Mobile Applications', 'Regression Testing', 'Security and Privacy', 'Automated Bug Detection', 'Search and APIs', 'Build and Package Management', 'Symbolic Execution', 'Apps and Energy', 'Requirements', 'Software Understanding', 'Configuration, Variability, and Clones', 'Other'])

def allowed_files(filename):
  """
  Checks if the file extension matches the list of allowed extensions
  """
  return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_FILES

def send_email(subject, sender, recipients, text_body, html_body):
  """
  Send email function
  """
  msg = Message(subject, sender=sender, recipients=recipients)
  msg.body = text_body
  msg.html = html_body
  mail.send(msg)

def get_email_token(payload, expires_in=6000):
  """
  By default the function returns a token that expires in 6000 seconds
  if passed None in expires_in => indefinite token
  """
  if expires_in:
    payload['exp'] = time() + expires_in
  return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')

def verify_email_token(token):
  """
  Verify's the email token is valid or not
  """
  try:
    payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
  except Exception as e:
    print("Something Happened: ", e)
    return
  return payload

def upload_file_to_s3(s3, file, bucket_name, acl="public-read"):
  """
  Uploading a given file object to AWS S3 bucket (using boto3 lib)
  """
  try:
    s3.upload_fileobj(
      file,
      bucket_name,
      file.filename,
      ExtraArgs={
        "ACL": acl,
        "ContentType": file.content_type
      }
    )
  except Exception as e:
    print("Something Happened: ", e)
    return e

def tags_obj_to_str(tags_array, delimiter=" "):
  """
  Converts the tags(model) into a string with the given delimiter
  """
  tags_str = ""
  for tag in tags_array:
    if tags_str != "":
      tags_str += delimiter
    tags_str += tag.tagname
  return tags_str

def files_to_str(files, delimiter=" "):
  """
  Converts the files(model) into a string with the given delimiter
  """
  file_pairs = ""
  for file in files:
    if file_pairs != "":
      file_pairs += delimiter
    file_pairs += "{}: {}".format(file.filetype, file.filename)
  return file_pairs

### Form custom validations

def valid_url_check(form, field):
  link_provided = (not not field.data)

  if link_provided:
    pattern = "(https:|http:)\/\/[[:alnum:]]*[.]*[\S]*"

    if not re.match(pattern, field.data):
      raise ValidationError("Not a valid url")

def accept_specific_links(form, field):
  link_provided = (not not field.data)

  if link_provided:
    pattern = "https:\/\/[[:alnum:]]*[.]*(regex101.com|github.com|softwareheritage.org)[\S]*"
    if not re.match(pattern, field.data):
      raise ValidationError("Links are accepted only from zenodo.com/github.com/softwareheritage.org")

def file_upload_or_link(form, field):
  link_provided = (not not form.linktotoolwebpage.data)
  file_provided = False

  for file in form.all_files.data:
    if (not not file):
      file_provided = True

  if not link_provided or not file_provided:
    raise ValidationError('You can provide a link to either zenodo.com/github.com/softwareheritage.org in the above field or upload here')

def file_validation(form, field):
  """
  File validation callback for forms
  """
  if field.data:
    for file in field.data:
      if isinstance(file, str):
        continue
      if not allowed_files(file.filename):
        raise ValidationError('File format not supported (supported: md, txt, pdf, docx, zip, gz, rar)')


##### elasticsearch utils

def add_to_index(index, model):
  """
  Adds the given model object to the elastic search indexes
  uses the searchable field to get the field names to be indexed
  """
  if not app.elasticsearch:
    return
  payload = {}

  for field in model.__searchable__:
    if field == 'tags':
      payload[field] = tags_obj_to_str(getattr(model, field))
    else:
      payload[field] = getattr(model, field)
    app.elasticsearch.index(index=index, doc_type=index, id=model.id, body=payload)

def remove_from_index(index, model):
  if not app.elasticsearch:
    return
  app.elasticsearch.delete(index=index, doc_type=index, id=model.id)

def query_index(index, query, page, per_page):
  """
  Method that actually queries the elasticsearch indexes
  indexes every field, takes pagination details as arguments
  """
  if not app.elasticsearch:
    return [], 0
  search = app.elasticsearch.search(index=index, doc_type=index, body={'query': {'multi_match': {'query': query, 'fields': ['*']}}, 
    'from': (page - 1) * per_page, 'size': per_page})
  ids = [int(hit['_id']) for hit in search['hits']['hits']]
  return ids, search['hits']['total']