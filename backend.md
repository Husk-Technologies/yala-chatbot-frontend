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
    "success": true,
    "message": "Funeral details verified successfully",
    "description": "Kukua Funeral",
    "uniqueCode": "DE2021",
    "guest": [
        "DE2345",
        "DE2022",
        "DE2021"
    ]
}

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
        "day": "Friday",
        "time": "2026-01-11T20:11:51.985Z",
        "name": "Philipo's Tilapia Joint ",
        "link": "https://maps.app.goo.gl/i4frXrX5ZNvpcHLG6"
    }
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
    "message":"Sorry for your lost my dear Kwesi."
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
POST {{base_url}}make-donation
The {{base_url}} variable is resolved from your active environment (e.g., the yala url environment).

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
URL: {{base_url}}make-donation
Body type: raw → JSON

Request body schema:


JSON

{
  "funeralUniqueCode": "DE2022",             // String. Unique code identifying the funeral.
  "guestId": "69764a754c55dc7bd8cda7d4",    // String. ID of the guest making the donation.
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
  "donationAllowed": false
}



















