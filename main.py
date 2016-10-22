# -*- coding: utf-8 -*-
import logging
from webapp2 import RequestHandler, Route, WSGIApplication
import jinja2
import os
import mimetypes
from datetime import datetime
import cloudstorage
from google.appengine.ext import blobstore, ndb
from google.appengine.api import images
from google.net.proto.ProtocolBuffer import ProtocolBufferDecodeError
from credentials import bucket


# Jinja2 environment variable
JENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname('main.py')),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True
    )


# Data Store class
class Photo(ndb.Model):
    serving_url = ndb.StringProperty()
    file_name = ndb.StringProperty()
    upload_date = ndb.DateTimeProperty()


class MainHandler(RequestHandler):
    """main page with upload form"""
    def home(self, template=JENV.get_template('templates/home.html')):
        logging.info('home page')
        message = self.request.get('message')
        success = self.request.get('success')
        t = template.render(message=message, success=success)
        self.response.write(t)


class UploadHandler(RequestHandler):
    """handle the upload of a photo"""
    def upload(self):
        logging.info('uploading photo')
        # get the file
        image = self.request.get("file")
        # check size
        if not image:
            self.error(400)
            logging.error('upload photo: no file')
            self.redirect('/home?message=no file uploaded')
            return
        mime_type = mimetypes.guess_type(self.request.POST['file'].filename)
        if not mime_type[0]:
            self.error(400)
            logging.error('upload photo: the file must be an image')
            self.redirect('/home?message=the file must be an image')
            return
        elif mime_type[0]:
            logging.info(mime_type)
            if 'image' not in mime_type[0]:
                self.error(400)
                logging.error('upload photo: the file must be an image')
                self.redirect('/home?message=the file must be an image')
                return

        # name of the file on the cloud storage -> must be unique!!
        upload_date = datetime.now()
        file_name = 'photo{}.jpg'.format(upload_date)
        # save the file on the cloud storage and get the url
        serving_url, key = make_file_from_content(image, file_name)
        logging.info(serving_url)
        logging.info(key)

        # add the photo to the datastore
        photo = Photo(
            upload_date=upload_date,
            serving_url=serving_url,
            file_name=file_name
        )
        photo.put()

        # redirect to the show page
        self.redirect('/?message=success')


class ShowHandler(RequestHandler):
    """show all the photos"""
    def show(self, template=JENV.get_template('templates/show.html')):
        logging.info('showing photos')
        # query on the atastore
        photos = Photo.query().fetch()
        p_l = []
        # create a list of dictionary
        for p in photos:
            p_l.append({'file_name': p.file_name,
                        'serving_url': p.serving_url,
                        'upload_date': p.upload_date,
                        'key': p.key.urlsafe()})
        t = template.render(photos=p_l)
        self.response.write(t)


class DeleteHandler(RequestHandler):
    """delete the selcted photo"""
    def delete(self):
        logging.info('delete photo')
        photo_key_urlsafe = self.request.get('photo_key')
        try:
            pkey = ndb.Key(urlsafe=photo_key_urlsafe)
            photo = pkey.get()
            logging.info(photo)
        except ProtocolBufferDecodeError as e:
            self.error(404)
            logging.error(e)
            self.response.out.write(e)
            return
        # check if there is the photo
        if not photo:
            self.error(404)
            msg = 'photo not found using the urlsafe key provided'
            logging.error(msg)
            self.response.out.write(msg)
            return

        if photo.file_name is not None:
            name = '/%s/%s' % (bucket, photo.file_name)
            # catch any error
            try:
                cloudstorage.delete(name)
            except Exception as e:
                self.error(500)
                logging.error(e)
                self.response.out.write(e)
                return

        # delete the photo on datastore
        pkey.delete()
        return


def make_file_from_content(content, photo_id):
    """
    save the file on cloud storage
    :param content: the photo
    :param photo_id identifier fot the photo (needed for the name)

    """

    gcs_file_name = '/%s/%s' % (bucket, photo_id)
    content_type = mimetypes.guess_type(photo_id)[0]

    with cloudstorage.open(gcs_file_name, 'w', content_type=content_type,
                           options={b'x-goog-acl': b'public-read'}) as f:
        f.write(content)

    key = blobstore.create_gs_key('/gs' + gcs_file_name)
    url = images.get_serving_url(key)

    return url, key


routes = [
    Route('/', handler='main.MainHandler:home'),
    Route('/home', handler='main.MainHandler:home'),
    Route('/upload', handler='main.UploadHandler:upload'),
    Route('/show', handler='main.ShowHandler:show'),
    Route('/delete', handler='main.DeleteHandler:delete')
]

app = WSGIApplication(routes, debug=True)
