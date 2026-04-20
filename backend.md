# Check Guest Registration
Purpose
Check whether a guest is already registered in the system using their phone number, and if found, return the guest details along with an access token.
Endpoint
Method: POST
URL: {{base_url}}check-guest-registration

{{base_url}} is an environment or collection variable that holds the base URL of the Yala API.
Request Body
Type: raw JSON
Content-Type: application/json

Example

JSON
{
  "phoneNumber": "233246155311"
}


Fields
phoneNumber (string, required) – Guest's phone number in international format (e.g., 233...). Used to look up the existing guest record.

Successful Response (200)
When the guest is found, the API responds with:

JSON

{
  "success": true,
  "message": "Guest fetched successfully.",
  "guest": {
    "_id": "697595562855de7055de25a8",
    "fullName": "Bullet",
    "phoneNumber": "233246155311",
    "createdAt": "2026-01-25T04:00:22.894Z",
    "updatedAt": "2026-01-25T18:00:50.811Z",
    "__v": 0,
    "funeralUniqueCode": [
      "DE2022"
    ]
  },
  "token": "<jwt-token>"
}


Response Fields
success (boolean) – Indicates if the guest lookup was successful.
message (string) – Human-readable status message.
guest (object) – The guest record returned from the system:
_id (string) – Unique identifier of the guest.
fullName (string) – Guest's full name.
phoneNumber (string) – Guest's phone number.
createdAt (string, ISO datetime) – When the guest was created.
updatedAt (string, ISO datetime) – When the guest was last updated.
__v (number) – Internal version field.
funeralUniqueCode (array of string) – One or more funeral codes associated with this guest.

token (string) – JWT token that can be used for subsequent authenticated requests (subject to your backend's auth rules).

# Register Guest
Register Guest
Registers a new guest in the system using their full name and phone number. On success, the API creates a guest record and returns an authentication token that can be used for subsequent authenticated operations (if supported by the backend).
HTTP Request
Method: POST
URL: {{base_url}}register-guest

Request Body
Send a JSON object with the following fields:

JSON

{
  "fullName": "Julliet Ameke",
  "phoneNumber": "233246152343"
}


fullName (string, required)
  The guests full name as it should appear in the system.
phoneNumber (string, required)
  The guests phone number, including country code (e.g., 233 for Ghana).

Successful Response
On success, the server returns:
Status: 201 Created
Body (example):

JSON

{
  "success": true,
  "message": "Guest registered successfully",
  "guest": {
    "fullName": "Julliet Ameke",
    "phoneNumber": "233246152343",
    "funeralUniqueCode": [],
    "_id": "<guest-id>",
    "createdAt": "<timestamp>",
    "updatedAt": "<timestamp>",
    "__v": 0
  },
  "token": "<jwt-token>"
}

success: Indicates whether the registration was successful.
message: Human-readable status message.
guest: The created guest object, including identifiers and timestamps.
token: A JWT or similar token issued for the newly registered guest.


# Get Funeral details
Purpose
This endpoint verifies funeral details for a guest or organiser based on a unique funeral code.
Method & URL
Method: GET
URL: {{base_url}}verify-funeral-details/:uniqueCode

Path Variables
uniqueCode (string, required)
A unique funeral code used to identify and verify the funeral details.
Example: DE2021

How to Call
Ensure {{base_url}} is set in the active environment (e.g., https://api.example.com/).
Replace :uniqueCode in the path with the actual funeral code you want to verify.
Example final URL: {{base_url}}verify-funeral-details/DE2021

Successful 200 Response
A 200 OK response with a body like:

JSON

{
"success"
:
true
,
"message"
:
"Funeral details verified successfully"
,
"description"
:
"Kukua Funeral"
,
"eventType"
:
"farewell"
 | 
"connect"
 | 
"celebrate"
 | 
"exhibit"
,
"uniqueCode"
:
"DE2021"
,
"guest"
:
[
"DE2345"
,
"DE2022"
,
"DE2021"
]
}

Yala farewell - We did too. So we built Yala Farewell. Share memorial programs, track attendance, collect condolences, and manage donations — all inside WhatsApp.


Yala Exhibit - Yala Exhibit helps exhibition organizers share floor plans, track attendance, capture leads, and connect exhibitors with attendees.

Yala Connect - Yala Connect helps conference organizers share agendas, register attendance, collect live speaker questions, gather feedback and access venue details.

Yala Celebrate - Yala Celebrate gives wedding videos program, guest attendance, well-wishes, and gifts all on WhatsApp. No printing. No QR codes.

indicates that:
success is true: the funeral details were verified.
message describes the outcome of the verification.
uniqueCode echoes the verified funeral code.
guest is an array of related guest or funeral codes associated with this verification.

A 404 error Not found error with a body like:
{
    "success": false,
    "message": "Sorry this event is closed."
}

should alert users that that event has been closed

# Get funeral brochure
Endpoint Details
Method: GET
Path: /funeral-brochure/:uniqueCode
Description: Fetches the funeral brochure for a given funeral event using its unique code.

Request
URL Parameters
uniqueCode (string, required)  
  The unique identifier assigned to a funeral event.

Headers
Standard authentication headers may be required depending on environment setup.

Example Request

Plain Text

GET https://yala-chatbot-backend.onrender.com/api/funeral-brochure/12345ABC

Response
Success (200 OK)


JSON

{
  "success": true,
  "message": "Funeral brochure fetched successfully",
  "brochureUrl": "https://res.cloudinary.com/.../yala_funeral_files/seogycdo75hnwvgcg6ji.pdf",
  "brochureDownloadCount": 1
}

Response Fields
success (boolean) – Indicates if the request was successful.
message (string) – Human-readable confirmation message.
brochureUrl (string) – Direct URL to the funeral brochure PDF file.
brochureDownloadCount (integer) – Number of times the brochure has been downloaded.

# Get funeral location
Overview
The Get Funeral Location endpoint retrieves the location details of a funeral event using its unique Endpoint Details
Method: GET
Path: /funeral-location/:uniqueCode
Description: Fetches the funeral location associated with a given funeral event code.

Request
URL Parameters
uniqueCode (string, required)
  The unique identifier assigned to a funeral event.

Headers
Standard authentication headers may be required depending on environment setup.

Example Request

Plain Text

GET {{base_url}}/funeral-location/12345ABC

Response
Success (200 OK)


JSON

{
    "success": true,
    "message": "Funeral location fetched successfully",
    "location": {
        "name": "Osu Funeral Home",
        "day": "Friday",
        "time": "2026-05-16T10:46:00.000Z",
        "link": "https://maps.app.goo.gl/hcQJuLjdNGbu2tWE8"
    },
    "date": "2026-02-20T00:00:00.000Z"
}

Response Fields
success (boolean) – Indicates if the request was successful.
message (string) – Human-readable confirmation message.
location (object) – Contains details of the funeral venue:
venue (string) – Name of the funeral venue.
address (string) – Full address of the venue.
latitude (float) – Geographical latitude of the venue.
longitude (float) – Geographical longitude of the venue.

# Submit Condolence
StartFragment
Overview
Submit a condolence message for a specific funeral and guest.
This endpoint creates a new condolence record associated with a funeral (via its unique code) and a guest.
Method: POST
URL: {{base_url}}condolence-submit

Request
Headers
Content-Type: application/json
Any additional auth headers, if required by the API (for example, Authorization).

Body
Send a JSON object:
JSON
{
    "funeralUniqueCode":"DE2022",
    "guestId":"6975a5dca73dfa0d03945fd6",
    "message":"Sorry for your lost my dear Kwesi.",
    "messageType":"defined" | "predefined",
}


Field details:
funeralUniqueCode string (required)
  Unique code that identifies the funeral to which the condolence relates.
guestId string (required)
  Identifier of the guest submitting the condolence.
message string (required)
  The condolence message text.

Responses
201 Created
On success, the API returns a JSON response similar to:


JSON

{
    "success": true,
    "message": "Condolence message submitted successfully.",
    "condolence": {
        "funeralUniqueCode": "DE2022",
        "guestId": "6975a5dca73dfa0d03945fd6",
        "message": "Sorry for your lost my dear Kwesi.",
        "_id": "697a66676fac8a43e2a31d27",
        "createdAt": "2026-01-28T19:41:27.621Z",
        "updatedAt": "2026-01-28T19:41:27.621Z",
        "__v": 0
    }
}

success – Indicates the operation was successful.
message – Human‑readable status message.
condolence – The created condolence record.

When the event is not accepting condolence messages this is how the final output will be:

{
    "success": false,
    "message": "Condolence messages are disabled for this funeral."
}

Possible error cases
Exact error formats may vary, but typical reasons for failure include:
Missing or invalid funeralUniqueCode
Missing or invalid guestId
Empty or invalid message
Authorization / authentication failures (if protected)

# Make donations
Overview
Initializes a donation for a funeral guest and returns a payment checkout URL (via Paystack).
POST https://api.yalasolution.com/api/make-donation
The https://api.yalasolution.com/api/ variable is resolved from your active environment (e.g., the yala url environment).

StartFragment
Authorization
This endpoint requires an authenticated request. If the token is invalid or missing, the API may return:


JSON

401 Unauthorized
{
  "success": false,
  "message": "Invalid token"
}

Request
Method: POST
URL: https://api.yalasolution.com/api/make-donation
Body type: raw → JSON

Request body schema:

JSON

{
  "funeralUniqueCode": "DE2022",             // String. Unique code identifying the funeral.
  "guestId": "69764a754c55dc7bd8cda7d4", 
    "referenceName": "Ama Akpaflo",
  "donationAmount": 2                       // Number. Donation amount (currency defined by backend).
}


Required fields
funeralUniqueCode (string) – identifies which funeral the donation is for.
guestId (string) – the guest who is donating.
donationAmount (number) – amount to be charged.

Example request body (current sample):

Successful Response (200)
On success, the API initializes the donation and returns a checkout URL for payment.
Example 200 response:

JSON

{
  "funeralUniqueCode": "DE2022",
  "guestId": "69764a754c55dc7bd8cda7d4",
  "donationAmount": 2
}


Response fields
success (boolean) – true if initialization succeeded.
message (string) – human-readable status message.
reference (string) – unique payment/donation reference.
url (string) – Paystack checkout URL; redirect the user here to complete payment.

Error Response – Donations Not Allowed (404)
If the funeral/event does not accept donations, the API returns a 404 Not Found response indicating that donations are not allowed for the specified funeralUniqueCode.
Status: 404 Not Found
Example response:

JSON

{
  "success": false,
  "message": "This event does not accept donations",
  "donationAllow

}

# Get Upload photo link
Fetch upload photo link for an event
Purpose
Returns the Google Drive folder link where photos for a specific event can be uploaded.
Request
GET {{base_url}}funeral-upload-photo-link/:uniqueCode
Required variables
{{base_url}} (environment variable, e.g. in environment yala url): Base URL for the API.
uniqueCode (path variable): The event’s unique code.

Path parameters
:uniqueCode (string, required) — Event unique code.
Example: CO2024


Response (200 OK)
Response body includes:
success (boolean) — Indicates whether the operation succeeded.
message (string) — Human-readable status message.
photoLink (string | null) — Google Drive folder URL to upload photos.

Example response:


JSON

{
  "success": true,
  "message": "Event upload photo link fetched successfully",
  "photoLink": "https://drive.google.com/drive/folders/<folderId>"
}
Usage example
1) Ensure base_url is set in the active environment.
2) Set the path variable uniqueCode.
Example URL:
{{base_url}}funeral-upload-photo-link/CO2024
Then send the request; use the returned photoLink to open the Google Drive folder for uploads.

# Get download photo link
Purpose
Fetch a shareable download link (Google Drive folder link) for event photos associated with a funeral/event identified by a unique code.
Endpoint
GET https://api.yalasolution.com/api/funeral-download-photo-link/:uniqueCode
Path variable
NameTypeRequiredExampleDescriptionuniqueCode

string

yes

CO2024

Unique code that identifies the funeral/event whose photo download link should be returned.

Required environment variable
This request expects the following variable to be defined in your active environment (currently: yala url):
VariableExampleDescriptionbase_url

https://api.example.com/

Base URL for the API (include trailing / if your API requires it).

Example request


Plain Text


GET https://api.yalasolution.com/api/funeral-download-photo-link/CO2024


Success response (200)
Response body (JSON)


JSON

{
  "success": true,
  "message": "Event download photo link fetched successfully",
  "photoLink": "https://drive.google.com/drive/folders/..."
}


Fields
FieldTypeDescriptionsuccess

boolean

Indicates whether the operation succeeded.

message

string

Human-readable status message.

photoLink

string (url)

A Google Drive folder link where photos can be downloaded.

Common error responses
Exact status codes/messages may vary depending on the API implementation.
400 Bad Request — Missing/invalid uniqueCode.
404 Not Found — No event found for the provided uniqueCode, or no photo folder/link exists.
401 Unauthorized / 403 Forbidden — Authentication/authorization failed (if the API is protected in your environment).
500 Internal Server Error — Unexpected server error.



















