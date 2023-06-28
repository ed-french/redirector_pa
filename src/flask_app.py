import logging
import os
from twilio.rest import Client
logging.basicConfig(level=logging.DEBUG)
import credentials
from twilio.http.http_client import TwilioHttpClient
from typing import Optional
import random

from flask import Response,redirect


from flask_sqlalchemy import SQLAlchemy

from flask import Flask,request
import datetime


#proxy_client = TwilioHttpClient(proxy={'http': os.environ['http_proxy'], 'https': os.environ['https_proxy']})

proxy_client = TwilioHttpClient()
proxy_client.session.proxies = {'https': os.environ['https_proxy']}

app = Flask(__name__)
URI = f"mysql://{credentials.MYSQL_USERNAME}:{credentials.MYSQL_PASSWORD}@{credentials.MYSQL_HOST_ADDRESS}:3306/{credentials.MYSQL_LINKS_DATABASE}"

logging.info(f"\n\n\n******************\n{URI}")
app.config["SQLALCHEMY_DATABASE_URI"]=URI
app.config["SQLALCHEMY_POOL_RECYCLE"]=280
db=SQLAlchemy(app)


class Link(db.Model):
    __tablename__="links"
    id=db.Column(db.Integer,primary_key=True)
    link_label=db.Column(db.Text)
    audience=db.Column(db.Text)
    destination=db.Column(db.Text)
    hit_count=db.Column(db.Integer)
    last_hit=db.Column(db.DateTime)

    def __str__(self):
        return f"{self.id},{self.link_label},{self.audience},{self.destination},{self.hit_count},{self.last_hit}"

    def get_html_table_row(self,key:str):
        cells=["<tr>"]
        make_cell=lambda content:f"<td>{content}</td>"

        cells.append(make_cell(self.id))
        cells.append(make_cell(f"""<a href="https://infuriatingpixels.pythonanywhere.com/link?{self.link_label}">{self.link_label}</a>"""))
        cells.append(make_cell(self.audience))
        cells.append(make_cell(self.hit_count))
        cells.append(make_cell(self.last_hit))

        cells.append(make_cell(f"""<a href="{self.destination}">{self.destination}"""))
        cells.append(make_cell(f"""<a href="/delete_link?link_id={self.id}&key={key}">Del</a>"""))
        cells.append("</tr>")
        res="".join(cells)
        return res


    @staticmethod
    def get_html_table_header()->str:
        res="""
        <table>
        <tr>
        <th>ID</th>
        <th>Link label</th>
        <th>Audience</th>
        <th>Hit count</th>
        <th>Last hit</th>
        <th>Destination URL</th>
        <th>Options</th>
        </tr>
        """
        return res

    @staticmethod
    def get_html_table_footer()->str:
        res="""
        </table>
        """
        return res


    @staticmethod
    def get_html_edit_row(key)->str:
        res=f"""
    <tr>
        <form method="post" action="/make_link">
            <input type="hidden" name="key" value="{key}" />
            <td>
            ..
            </td>
            <td>
                <input type="text" name="link_label" />
            </td>
            <td>
                <input type="text" name="audience" />
            </td>
            <td>...</td>
            <td>...</td>
            <td>
                <input type="text" name="destination" />
            </td>
            <td>
                <input type="submit" value="Submit" />
            </td>
        </form>
    </tr>
        """
        return res



db.create_all()
db.session.commit()




replies={"Flic":"Felicity, you will regret complaining that I'm too slow. Now I intend to give you a lecture on not hurting the feelings of a robotic gate before I will open. Serves you right!",
            "Josephine":"Top of the morning to you Josephine. Welcome home. Enjoy my openness.",
            "Ed":"I. Shall. Obey.",
            "Dominic":"I am surprised you ever bothered to open the gate, but it is now done."}


def sendSMS(content:str,destination:Optional[str]=None)->None:
    """
        Sends SMS using Twilio
    """
    if destination is None:
        destination=credentials.GATE_PHONE_NUMBER
    logging.info(f"Sending SMS {content} to {destination}")
    account_sid = credentials.TWILIO_SID
    auth_token = credentials.TWILIO_SECRET
    client = Client(account_sid, auth_token,http_client=proxy_client)
    message = client.messages \
                .create(
                     body=content,
                     from_=credentials.TWILIO_PHONE_NUMBER,
                     to=destination,
                 )


    logging.info(message.sid)

def international_to_national(caller_no_raw):
    logging.debug(f"Raw caller no: {caller_no_raw}")
    if caller_no_raw.startswith("+44"):
        caller_no="0"+caller_no_raw[3:]
        logging.info(f"Truncated to local no: {caller_no}")
    else:
        caller_no=caller_no_raw
    return caller_no

def authorised(caller_no:str):
    """
            Checks is the user is authorised
            returns the user name if they are
            or False

            credentials.USERS is a dict where:
                key is the name and
                value is the number in local format
    """
    if caller_no not in credentials.USERS.values():
        logging.info("Phone number not recognised")
        return False
    for name,number in credentials.USERS.items():
        if number==caller_no:
            logging.info("Phone number was recognised as being a user")
            return name

    return 'Unknown user. Please tell Ed the secret word "fishcakes"'



@app.route('/')
def hello_world():
    logging.info("Hello world endpoint hit z")
    return 'Hello!'


@app.route('/link')
def link():
    link_id=request.query_string.decode()
    ip_address:str=request.headers['X-Real-IP']

    logging.info(f"Link hit...{link_id} for {ip_address}")


    # Fetch all the records
    records=Link.query.all()

    matches=[record for record in records if record.link_label==link_id]

    if not len(matches)==1:
        return Response("Invalid link", 400)

    destination_link=matches[0]

    # increment the count
    destination_link.hit_count=Link.hit_count+1

    # update the date
    destination_link.last_hit=datetime.datetime.now()

    db.session.commit()

    # Send SMS

    message=f"""{destination_link.link_label} hit for {ip_address} to visit {destination_link.destination}
    https://infuriatingpixels.pythonanywhere.com/list_links?key={credentials.LINK_API_KEY}"""
    sendSMS(message,credentials.USERS["Ed"])



    return redirect(matches[0].destination , code=302)



@app.route('/delete_link')
def delete_link():
    key:str=request.args.get("key")
    logging.info(f"Request to list the links with key of {key}")
    # TEST FOR KEY HERE...
    if not key==credentials.LINK_API_KEY:
        logging.info("Bad key")
        return Response("Not Authorised", 401)

    link_id:int=int(request.args.get("link_id"))
    all_rows=Link.query.all()

    matches=[record for record in all_rows if record.id==link_id]

    if not len(matches)==1:
        return Response(f"Invalid link- found {len(matches)} for id={link_id}", 400)


    db.session.delete(matches[0])

    db.session.commit()

    return redirect(f"/list_links?key={key}",302)







@app.route('/list_links')
def list_links():
    key:str=request.args.get("key")
    logging.info(f"Request to list the links with key of {key}")
    # TEST FOR KEY HERE...
    if not key==credentials.LINK_API_KEY:
        logging.info("Bad key")
        return Response("Not Authorised", 401)

    # Show the links
    results=Link.query.all()

    raw=["<html><body>"]

    raw.append(f"{Link.get_html_table_header()}")
    for row in results:
        raw.append(row.get_html_table_row(key))


    raw.append(Link.get_html_edit_row(key))

    raw.append(Link.get_html_table_footer())



    raw.append("</body></html>")



    return "\n".join(raw)


@app.route('/make_link', methods=["POST"])
def make_link():
    key=request.values.get("key")

    id=random.randint(0,1000000000)
    link_label=request.values.get("link_label")
    audience=request.values.get("audience")
    destination=request.values.get("destination")
    hit_count=0
    last_hit=datetime.datetime.now()


    # check key here
    if not key==credentials.LINK_API_KEY:
        return Response("Not Authorised", 401)

    insert_this=Link(id=id,
                    link_label=link_label,
                    audience=audience,
                    destination=destination,
                    hit_count=hit_count,
                    last_hit=last_hit)
    db.session.add(insert_this)
    db.session.commit()
    return redirect(f"/list_links?key={key}",302)




@app.route('/make_link_page')
def make_link_page():
    key=request.args.get("key","no key provided")

    # check key here
    if not key==credentials.LINK_API_KEY:
        return Response("Not Authorised", 401)
    res=f"""
    <html>
    <head></head>
    <body>
        <form method="post" action="/make_link">
        <input type="hidden" name="key" value="{key}" />
        Link label:<input type="text" name="link_label" /><br />
        Audience:<input type="text" name="audience" /><br />
        Destination url:<input type="text" name="destination" /> <br />
        <input type="submit" value="Submit" />
        </form>
    </body>
    </html>
    """
    return res


@app.route('/inbound_sms',methods=["POST"])
def inbound_sms():
    """
        Forwards sms to the modem in case sent to the wrong number
    """
    logging.info("Inbound SMS received_._._")
    logging.info(request.values)
    caller_no_raw=request.values.get("From")
    caller_no=international_to_national(caller_no_raw)
    logging.info("SMS was sent from {caller_no}")
    user=authorised(caller_no)
    if user is False:
        """
            Quietly ignore unauthorised SMS
        """
        logging.info("Unauthorised SMS ignored")
        return "<Response></Response>"
    logging.info("SMS being forwarded")

    body=request.values["Body"]
    if body.upper()=="OPEN":
        body+=f" for {caller_no_raw}"
    sendSMS(body)




    return "<Response></Response>"

@app.route('/inbound_call',methods=["POST"])
def inbound_call():
    """
        Receives twilio webhook and opens gate for known users in credentials.py
    """
    logging.info("inbound call enpoint hit")


    logging.info(request.values)
    caller_no_raw=request.values.get("Caller")
    caller_no=international_to_national(caller_no_raw)
    logging.debug(f"Caller no: {caller_no}")


    person=authorised(caller_no)
    if person is False:
        logging.info("User not recognised")

        return """
        <?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="man" language="en-GB">Gate will not open for you, be gone with you!</Say>
</Response>"""



    # Authosied, so :
    #               Open gate by sending SMS
    logging.info("User recognised, opening gate will be sent")

    sendSMS(content=f"OPEN for {caller_no_raw}")

    logging.info("Gate open sent")

    voice=random.choice(["man","woman"])
    language=random.choice(["en-US","en-GB"])



    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Say voice="{voice}" language="{language}">{replies[person]}</Say>
</Response>"""