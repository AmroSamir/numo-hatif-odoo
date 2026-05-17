---
title: Default module
language_tabs:
  - shell: Shell
  - http: HTTP
  - javascript: JavaScript
  - ruby: Ruby
  - python: Python
  - php: PHP
  - java: Java
  - go: Go
toc_footers: []
includes: []
search: true
code_clipboard: true
highlight_theme: darkula
headingLevel: 2
generator: "@tarslib/widdershins v4.0.30"

---

# Default module

API for managing WhatsApp message flows

Base URLs:

* <a href="https://api.voxa.sa">Prod Env: https://api.voxa.sa</a>

# Authentication

- HTTP Authentication, scheme: bearer

- HTTP Authentication, scheme: bearer

- HTTP Authentication, scheme: bearer

- oAuth2 authentication. 

    - Flow: clientCredentials

    - Token URL = [https://your-auth-server/connect/token](https://your-auth-server/connect/token)

|Scope|Scope Description|
|---|---|
|VoxaAPI|Access Voxa API as a service account|

# Account API

## POST Service Login

POST /connect/token

> Body Parameters

```yaml
client_id: ""
client_secret: ""
grant_type: client_credentials
scope: VoxaAPI

```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| no |none|
|» client_id|body|string| yes |Provided by Hatif Team|
|» client_secret|body|string| yes |Provided by Hatif Team|
|» grant_type|body|string| yes |Provided by Hatif Team|
|» scope|body|string| yes |Provided by Hatif Team|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

# Channels API

## GET Get Channels

GET /v1/channels/service-account

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|SkipCount|query|string| no |none|
|MaxResultCount|query|string| no |none|

> Response Examples

> 200 Response

```json
{
  "totalCount": 0,
  "items": [
    null
  ]
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

*ChannelListResponse*

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» totalCount|integer|true|none||none|
|» items|[any]|true|none||none|

# Whatsapp API

## POST Send Text

POST /v1/whatsapp/service-account/sendText

> Body Parameters

```json
{
    "ChannelId": "3a197.........",
    "Text": "Hey from Hatif 👋",
    "ToNumber": "9665xxxxxxxx"
}
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|Authorization|header|string| yes |none|
|content-type|header|string| yes |none|
|body|body|object| yes |none|
|» ChannelId|body|string| yes |none|
|» Text|body|string| yes |none|
|» ToNumber|body|string| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## POST Send Template

POST /v1/whatsapp/service-account/sendTemplate

Send a WhatsApp template message to a recipient using a pre-approved template.

  Templates are messages pre-registered and approved by Meta. They can include dynamic variables in the header, body, and buttons that you fill in at send time using the `Parameters` array.

  ---

  ## Parameters Array

  Each entry in `Parameters` targets a specific **component** of the template. The `Type` field determines which component you're filling:

  | Type | Purpose |
  |---|---|
  | `Header` | Fills the template header — can be text, image, document, or video |
  | `Body` | Fills `{{1}}`, `{{2}}`, etc. placeholders in the message body |
  | `Buttons` | Fills dynamic variables in URL or quick reply buttons |

  ---

  ## Body Parameters

  Body variables are positional — the order of items in `Values` maps to `{{1}}`, `{{2}}`, `{{3}}`, etc.

  ```json
  {
    "Type": "Body",
    "Values": [
      { "Type": "text", "Text": "value for {{1}}" },
      { "Type": "text", "Text": "value for {{2}}" }
    ]
  }
  ```

  ---

  ## Header Parameters

  If the template has a media header (image, video, or document), you can provide it explicitly. **If you omit the header parameter, the system will auto-populate it from the template's example media when
  available.**

  **Image header:**
  ```json
  {
    "Type": "Header",
    "Values": [
      { "Type": "image", "ImageUrl": "https://example.com/image.jpg" }
    ]
  }
  ```

  **Document header:**
  ```json
  {
    "Type": "Header",
    "Values": [
      {
        "Type": "document",
        "DocumentUrl": "https://example.com/file.pdf",
        "DocumentFilename": "Invoice.pdf"
      }
    ]
  }
  ```

  **Video header:**
  ```json
  {
    "Type": "Header",
    "Values": [
      { "Type": "video", "VideoUrl": "https://example.com/video.mp4" }
    ]
  }
  ```

  **Text header:**
  ```json
  {
    "Type": "Header",
    "Values": [
      { "Type": "text", "Text": "Your Order Update" }
    ]
  }
  ```

  ---

  ## Button Parameters

 There are two critical rules:

  ### Rule 1: Each button is a separate entry

  Unlike body parameters where all variables go into one `Values` array, **each button must be its own separate object** in the `Parameters` array.

  ### Rule 2: SubType and Index are required

  Every button entry must include:
  - **`SubType`** — the button type: `"url"` or `"quick_reply"`
  - **`Index`** — the button position: `"0"` for the first button, `"1"` for the second, `"2"` for the third

  ### URL Buttons

  URL button templates define a base URL with a dynamic suffix, e.g. `https://example.com/orders/{{1}}`. You only provide the **dynamic part**, not the full URL.

  ```json
  {
    "Type": "Buttons",
    "SubType": "url",
    "Index": "0",
    "Values": [
      { "Type": "text", "Text": "ORD-5123" }
    ]
  }
  ```
  This would produce a button linking to `https://example.com/orders/ORD-5123`.

  ### Quick Reply Buttons

  Quick reply button values define the **payload** sent back to your webhook when the customer taps the button. This is not the button label — the label is defined in the template itself.

  ```json
  {
    "Type": "Buttons",
    "SubType": "quick_reply",
    "Index": "0",
    "Values": [
      { "Type": "text", "Text": "confirm_order_123" }
    ]
  }
  ```

  ### Static buttons don't need parameters

  If a button has **no dynamic variable** (e.g. a fixed phone number button or a URL with no `{{1}}`), you do **not** need to include it in `Parameters`. Only buttons with dynamic content require parameter
  entries.

  ---

  ## Examples

  Check the request examples for different types of templates.

> Body Parameters

```json
{
    "ChannelId": "3a197b.....",
    "TemplateName": "order_confirmation1",
    "Language": "en",
    "ToNumber": "9665...",
    "Parameters": [
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Variable 1"
                },
                {
                    "Type": "text",
                    "Text": "Variable 1"
                },
                {
                    "Type": "text",
                    "Text": "Variable 1"
                }
            ]
        }
    ]
}
```

```json
{
    "ChannelId": "3a197xxxxxxxxxxx",
    "TemplateName": "order_confirmation",
    "Language": "en",
    "ToNumber": "966501234567",
    "Parameters": [
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Ahmed"
                },
                {
                    "Type": "text",
                    "Text": "#ORD-5123"
                },
                {
                    "Type": "text",
                    "Text": "confirmed"
                }
            ]
        }
    ]
}
```

```json
{
    "ChannelId": "3a197bxxxxxxxxxxxxxxx",
    "TemplateName": "order_tracking",
    "Language": "en",
    "ToNumber": "966501234567",
    "Parameters": [
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Ahmed"
                },
                {
                    "Type": "text",
                    "Text": "#ORD-5123"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "url",
            "Index": "0",
            "Values": [
                {
                    "Type": "text",
                    "Text": "ORD-5123"
                }
            ]
        }
    ]
}
```

```json
{
    "ChannelId": "3a197bxxxxxxxxxxxxx",
    "TemplateName": "appointment_reminder",
    "Language": "en",
    "ToNumber": "966501234567",
    "Parameters": [
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Ahmed"
                },
                {
                    "Type": "text",
                    "Text": "Feb 28, 2026 at 10:00 AM"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "quick_reply",
            "Index": "0",
            "Values": [
                {
                    "Type": "text",
                    "Text": "confirm_apt_123"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "quick_reply",
            "Index": "1",
            "Values": [
                {
                    "Type": "text",
                    "Text": "cancel_apt_123"
                }
            ]
        }
    ]
}
```

```json
{
    "ChannelId": "3a197bxxxxxxxxxxxxxx",
    "TemplateName": "promotion_offer",
    "Language": "en",
    "ToNumber": "966501234567",
    "Parameters": [
        {
            "Type": "Header",
            "Values": [
                {
                    "Type": "image",
                    "ImageUrl": "https://cdn.example.com/promo-banner.jpg"
                }
            ]
        },
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Ahmed"
                },
                {
                    "Type": "text",
                    "Text": "winter collection"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "url",
            "Index": "0",
            "Values": [
                {
                    "Type": "text",
                    "Text": "winter-2026"
                }
            ]
        }
    ]
}
```

```json
{
    "ChannelId": "3a197bxxxxxxxxxxxx",
    "TemplateName": "invoice_delivery",
    "Language": "ar",
    "ToNumber": "966501234567",
    "Parameters": [
        {
            "Type": "Header",
            "Values": [
                {
                    "Type": "document",
                    "DocumentUrl": "https://cdn.example.com/invoices/INV-2026-001.pdf",
                    "DocumentFilename": "Invoice-001.pdf"
                }
            ]
        },
        {
            "Type": "Body",
            "Values": [
                {
                    "Type": "text",
                    "Text": "Ahmed"
                },
                {
                    "Type": "text",
                    "Text": "1,250.00 SAR"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "url",
            "Index": "0",
            "Values": [
                {
                    "Type": "text",
                    "Text": "INV-2026-001"
                }
            ]
        },
        {
            "Type": "Buttons",
            "SubType": "quick_reply",
            "Index": "1",
            "Values": [
                {
                    "Type": "text",
                    "Text": "payment_received_INV001"
                }
            ]
        }
    ]
}
```

```json
"ChannelId": "3a197bxxxxxxxxxxxxxx",
"TemplateName": "product_demo",
"Language": "en",
"ToNumber": "966501234567",
"Parameters": [
    {
        "Type": "Header",
        "Values": [
            {
                "Type": "video",
                "VideoUrl": "https://cdn.example.com/demos/product-tour.mp4"
            }
        ]
    },
    {
        "Type": "Body",
        "Values": [
            {
                "Type": "text",
                "Text": "Ahmed"
            }
        ]
    }
]
}
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|Authorization|header|string| yes |none|
|content-type|header|string| yes |none|
|body|body|object| yes |none|
|» ChannelId|body|string| yes |Channel Id to be used.|
|» TemplateName|body|string| yes |An approved template name.|
|» Language|body|string| yes |none|
|» ToNumber|body|string| yes |Number to send to, use country code|
|» Parameters|body|[object]| yes |none|
|»» Type|body|string| yes |template component, could be: Header, Body, Footer or Buttons|
|»» Values|body|[object]| yes |none|
|»»» Type|body|string| yes |text, image, document, video|
|»»» Text|body|string| no |none|
|»»» ImageUrl|body|string| no |none|
|»»» DocumentUrl|body|string| no |none|
|»»» VideoUrl|body|string| no |none|

> Response Examples

> 200 Response

```json
{
    "contactId": "3a18a7e6-48bf-e5b8-4935-867e4b6c6c02",
    "status": "accepted",
    "message": "Template message sent successfully",
    "conversationEventId": "3a1e1287-9c7e-84fc-6eac-c530a49732ea"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

# Contact

## PUT Set Property Value on Contact

PUT /v1/contacts/contactId/propertiesproperty_id

> Body Parameters

```json
{
    "value": "Lead"
  }
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| yes |none|

> Response Examples

> 200 Response

```json
{
  "workspaceId": "string",
  "name": "string",
  "phoneNumber": "string",
  "contactType": 0,
  "email": "string",
  "company": "string",
  "position": "string",
  "customFields": {
    "ww": null
  },
  "notes": [
    {
      "contactId": "string",
      "text": "string",
      "creatorName": "string",
      "lastModificationTime": null,
      "lastModifierId": null,
      "creationTime": "string",
      "creatorId": "string",
      "id": "string"
    }
  ],
  "customProperties": [
    {
      "propertyDefinitionId": "string",
      "propertyName": "string",
      "propertyType": 0,
      "textValue": null,
      "numberValue": null,
      "dateValue": null,
      "selectValue": "string"
    }
  ],
  "lastModificationTime": "string",
  "lastModifierId": null,
  "creationTime": "string",
  "creatorId": "string",
  "id": "string"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» workspaceId|string|true|none||none|
|» name|string|true|none||none|
|» phoneNumber|string|true|none||none|
|» contactType|integer|true|none||none|
|» email|string|true|none||none|
|» company|string|true|none||none|
|» position|string|true|none||none|
|» customFields|object|true|none||none|
|»» ww|null|true|none||none|
|» notes|[object]|true|none||none|
|»» contactId|string|true|none||none|
|»» text|string|true|none||none|
|»» creatorName|string|true|none||none|
|»» lastModificationTime|null|true|none||none|
|»» lastModifierId|null|true|none||none|
|»» creationTime|string|true|none||none|
|»» creatorId|string|true|none||none|
|»» id|string|true|none||none|
|» customProperties|[object]|true|none||none|
|»» propertyDefinitionId|string|false|none||none|
|»» propertyName|string|false|none||none|
|»» propertyType|integer|false|none||none|
|»» textValue|null|false|none||none|
|»» numberValue|null|false|none||none|
|»» dateValue|null|false|none||none|
|»» selectValue|string|false|none||none|
|» lastModificationTime|string|true|none||none|
|» lastModifierId|null|true|none||none|
|» creationTime|string|true|none||none|
|» creatorId|string|true|none||none|
|» id|string|true|none||none|

## POST Get Contacts Search 

POST /v1/contacts/search

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|SkipCount|query|string| yes |none|
|MaxResultCount|query|string| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## DELETE Delete Property Value on Contact

DELETE /v1/contacts/3a18a7e6-48bf-e5b8-4935-867e4b6c6c02/properties/3a1d7c79-903d-73b4-c400-1fe5df9828e5

> Response Examples

> 200 Response

```json
{
  "workspaceId": "string",
  "name": "string",
  "phoneNumber": "string",
  "contactType": 0,
  "email": "string",
  "company": "string",
  "position": "string",
  "customFields": {
    "ww": null
  },
  "notes": [
    {
      "contactId": "string",
      "text": "string",
      "creatorName": "string",
      "lastModificationTime": null,
      "lastModifierId": null,
      "creationTime": "string",
      "creatorId": "string",
      "id": "string"
    }
  ],
  "customProperties": [
    {
      "propertyDefinitionId": "string",
      "propertyName": "string",
      "propertyType": 0,
      "textValue": null,
      "numberValue": null,
      "dateValue": null,
      "selectValue": "string"
    }
  ],
  "lastModificationTime": "string",
  "lastModifierId": null,
  "creationTime": "string",
  "creatorId": "string",
  "id": "string"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» workspaceId|string|true|none||none|
|» name|string|true|none||none|
|» phoneNumber|string|true|none||none|
|» contactType|integer|true|none||none|
|» email|string|true|none||none|
|» company|string|true|none||none|
|» position|string|true|none||none|
|» customFields|object|true|none||none|
|»» ww|null|true|none||none|
|» notes|[object]|true|none||none|
|»» contactId|string|true|none||none|
|»» text|string|true|none||none|
|»» creatorName|string|true|none||none|
|»» lastModificationTime|null|true|none||none|
|»» lastModifierId|null|true|none||none|
|»» creationTime|string|true|none||none|
|»» creatorId|string|true|none||none|
|»» id|string|true|none||none|
|» customProperties|[object]|true|none||none|
|»» propertyDefinitionId|string|false|none||none|
|»» propertyName|string|false|none||none|
|»» propertyType|integer|false|none||none|
|»» textValue|null|false|none||none|
|»» numberValue|null|false|none||none|
|»» dateValue|null|false|none||none|
|»» selectValue|string|false|none||none|
|» lastModificationTime|string|true|none||none|
|» lastModifierId|null|true|none||none|
|» creationTime|string|true|none||none|
|» creatorId|string|true|none||none|
|» id|string|true|none||none|

## POST Create Contact

POST /v1/contacts

> Body Parameters

```json
{
  "Name": "John Doe",
  "PhoneNumber": "5662567890",
  "Email": "john.doe@example.com",
  "Company": "Acme Corp",
  "Position": "Software Engineer"
}
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| no |none|
|» Name|body|string| yes |none|
|» PhoneNumber|body|string| yes |none|
|» Email|body|string¦null| no |none|
|» Company|body|string¦null| no |none|
|» Position|body|string¦null| no |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## GET Get Contacts

GET /v1/contacts

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|SkipCount|query|string| yes |none|
|MaxResultCount|query|string| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## PUT Update Contact

PUT /v1/contacts/3a1acd3b-c643-185d-d471-50efd3208988

> Body Parameters

```json
{
  "Position": "ss",
  "name": "ahmeddd",
"phoneNumber": "+966556779528"
}
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| no |none|
|» Position|body|string| yes |none|
|» name|body|string| yes |none|
|» phoneNumber|body|string| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## GET Get Contact By Id

GET /v1/contacts/3a18a7e6-48bf-e5b8-4935-867e4b6c6c02

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## DELETE Delete Contact

DELETE /v1/contacts/3a184c35-9bf2-dc78-24cd-62280d8604d7

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## POST Create Bulk Contacts vCards

POST /v1/contacts/import/vcards

> Body Parameters

```json
{
    "VCards": [
        "BEGIN:VCARD\nVERSION:3.0\nN:;Name شركة Name;;;\nFN:Name Name الوسائل\nX-WA-BIZ-NAME:Name\nORG:;\nTEL;type=CELL;type=VOICE;waid=966545614020:+966 55 555 5555\nEND:VCARD"
    ]
}
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|Accept|header|string| yes |none|
|body|body|object| no |none|
|» VCards|body|[string]| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## GET Contacts History

GET /v1/contacts/3a1ca96b-4a88-d947-725d-3fae66b3850d/history

> Response Examples

> 200 Response

```json
{"totalCount":2,"items":[{"id":"3a1fbb66-4353-8878-5129-aa7439c7e2db","propertyName":"Company","oldValue":null,"newValue":"شركة واو","creationTime":"2026-03-01T14:47:18.501081","creatorId":"3a1813e8-790f-26ac-c4b3-3a068eb70b08"},{"id":"3a1fbb66-4350-11a9-8b03-4112bb5f06d5","propertyName":"Email","oldValue":null,"newValue":"yousuf@test.com","creationTime":"2026-03-01T14:47:18.500643","creatorId":"3a1813e8-790f-26ac-c4b3-3a068eb70b08"}]}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

# Contact Properties

## GET List Contact Properties

GET /v1/contact-property-definitions

> Response Examples

> 200 Response

```json
[
  null
]
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

## POST Create Contact Property

POST /v1/contact-property-definitions

> Body Parameters

```json
{
    "name": "Status3",
    "type": "Select",
    "isRequired": false,
    "selectOptions": [
      { "value": "Lead", "color": "#FF5733" },
      { "value": "Customer", "color": "#33FF57" },
      { "value": "VIP", "color": null }
    ]
  }
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| yes |none|

> Response Examples

> 200 Response

```json
{
  "workspaceId": "string",
  "name": "string",
  "key": "string",
  "type": 0,
  "isRequired": true,
  "selectOptions": [
    "string"
  ],
  "lastModificationTime": null,
  "lastModifierId": null,
  "creationTime": "string",
  "creatorId": "string",
  "id": "string"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» workspaceId|string|true|none||none|
|» name|string|true|none||none|
|» key|string|true|none||none|
|» type|integer|true|none||none|
|» isRequired|boolean|true|none||none|
|» selectOptions|[string]|true|none||none|
|» lastModificationTime|null|true|none||none|
|» lastModifierId|null|true|none||none|
|» creationTime|string|true|none||none|
|» creatorId|string|true|none||none|
|» id|string|true|none||none|

## DELETE Delete Contact Property

DELETE /v1/contact-property-definitions/id

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|204|[No Content](https://tools.ietf.org/html/rfc7231#section-6.3.5)|none|None|

## PUT Update Contact Property

PUT /v1/contact-property-definitions/id

> Body Parameters

```json
  {
    "name": "Status3",
    "isRequired": true,
    "selectOptions": [
      { "value": "Lead", "color": "#FF5733" },
      { "value": "Customer", "color": "#33FF57" },
      { "value": "VIP", "color": "#5733FF" },
      { "value": "Churned", "color": "#888888" }
    ]
  }
```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|body|body|object| yes |none|

> Response Examples

> 200 Response

```json
{
  "workspaceId": "string",
  "name": "string",
  "key": "string",
  "type": 0,
  "isRequired": true,
  "selectOptions": [
    "string"
  ],
  "lastModificationTime": "string",
  "lastModifierId": "string",
  "creationTime": "string",
  "creatorId": "string",
  "id": "string"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» workspaceId|string|true|none||none|
|» name|string|true|none||none|
|» key|string|true|none||none|
|» type|integer|true|none||none|
|» isRequired|boolean|true|none||none|
|» selectOptions|[string]|true|none||none|
|» lastModificationTime|string|true|none||none|
|» lastModifierId|string|true|none||none|
|» creationTime|string|true|none||none|
|» creatorId|string|true|none||none|
|» id|string|true|none||none|

## GET Contact Properties Statistics

GET /v1/contact-property-definitions/{id}/statistics

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|id|path|string| yes |none|

> Response Examples

> 200 Response

```json
[
  "string"
]
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

# Support API

## POST Upload Audio File

POST /v1/support/upload-audio

Upload any Audio file to be used at Hatif.

Converts the input file to a WAV audio file (8kHz, mono, pcm_s16le) to be compatibile with telephony netwroks.

Maximum file size should not exceede 10 MB, any audio format is acceptable.

> Body Parameters

```yaml
audioFile: ""

```

### Params

|Name|Location|Type|Required|Description|
|---|---|---|---|---|
|Content-Type|header|string| yes |none|
|body|body|object| no |none|
|» audioFile|body|string(binary)| yes |none|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|
|400|[Bad Request](https://tools.ietf.org/html/rfc7231#section-6.5.1)|none|Inline|

### Responses Data Schema

# Outbound IVR API

## POST Create Outbound IVR

POST /v1/outbound-ivr

Starts an Outbound IVR call and plays an audio file (or used Text To Speech).
Fires a webhook request to `webhookUrl` after the call terminates.

> Body Parameters

```json
{
    "ChannelId": "3a197b6e-xxxx-xxxx-xxxx-5c2bc394dccd",
    "ExternalId": "myUniqueId",
    "DestinationNumber": "9665xxxxxxxx",
    "AudioFileUrl": null,
    "TtsText": "Dear Customer, to confirm your appointment please press 1, to cancel please press 32.",
    "TtsVoice": "Female",
    "WelcomeMessageFileUrl": null,
    "SuccessMessageFileUrl": null,
    "FailedMessageFileUrl": null,
    "Options": [
        {
            "Digit": "1",
            "Description": "Confirm"
        },
        {
            "Digit": "3",
            "Description": "Cancel"
        }
    ],
    "WebhookUrl": "https://webhook.site/2512f5b3-f389-4338-89dd-c9903bb5120a",
    "MaxAudioRetries": 3,
    "InputTimeoutMs": 6000,
    "DigitTimeoutMs": 3000
}
```

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|body|body|object| yes | CreateOutboundIvrRequestDto|none|
|» channelId|body|string(uuid)| yes ||Channel ID to use for the call.|
|» externalId|body|string¦null| no ||Optional external ID for idempotency.|
|» destinationNumber|body|string| yes ||Destination phone number.|
|» audioFileUrl|body|string(uri)¦null| no ||URL to the audio file to play (must be accessible via HTTP/HTTPS and only WAV format are accepted).|
|» ttsText|body|string¦null| no ||Text to convert to speech (alternative to AudioFileUrl)|
|» ttsVoice|body|string¦null| no ||Voice gender for TTS generation (Female or Male)|
|» welcomeMessageFileUrl|body|string¦null| no ||URL to the audio file to play as a welcom message before ttsText or audioFileUrl (must be accessible via HTTP/HTTPS and only WAV format are accepted).|
|» successMessageFileUrl|body|string(uri)¦null| no ||URL to the audio file to play as a success message after a valid entry (must be accessible via HTTP/HTTPS and only WAV format are accepted).|
|» failedMessageFileUrl|body|string(uri)¦null| no ||URL to the audio file to play as a failure message after an invalid entry (must be accessible via HTTP/HTTPS and only WAV format are accepted).|
|» options|body|[any]| yes ||Valid IVR options to be entered, Digit must be 0-9, *, or #.|
|» webhookUrl|body|string(uri)| yes ||Webhook URL to call when the IVR call completes.|
|» maxAudioRetries|body|integer| no ||Maximum number of times to retry playing the audio if no input is received (0-5)|
|» inputTimeoutMs|body|integer| no ||Timeout in milliseconds to wait for input (1000-30000)|
|» digitTimeoutMs|body|integer| no ||Inter-digit timeout in milliseconds (1000-10000).|

#### Description

**» audioFileUrl**: URL to the audio file to play (must be accessible via HTTP/HTTPS and only WAV format are accepted).

Alternative to TtsText - provide either AudioFileUrl OR TtsText

**» ttsText**: Text to convert to speech (alternative to AudioFileUrl)
Provide either AudioFileUrl OR TtsText (not both)

**» webhookUrl**: Webhook URL to call when the IVR call completes.

HMAC Signature can be provided by Hatif Team.

**» digitTimeoutMs**: Inter-digit timeout in milliseconds (1000-10000).
Used when multiple digits need to be entered.

#### Enum

|Name|Value|
|---|---|
|» ttsVoice|Male|
|» ttsVoice|Female|

> Response Examples

> 200 Response

```json
{
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx",
    "workspaceId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx",
    "channelId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx",
    "externalId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxxx",
    "destinationNumber": "+9665xxxxxxx",
    "audioFileUrl": "https://xxxxxx.wav",
    "ttsText": "Dear Customer, to confirm your appointment please press 1, to cancel please press 2.",
    "ttsVoice": 1,
    "audioType": 2,
    "options": [
        {
            "digit": "1",
            "description": "Confirm"
        },
        {
            "digit": "2",
            "description": "Cancel"
        }
    ],
    "webhookUrl": "https://xxxxxxx",
    "maxAudioRetries": 3,
    "inputTimeoutMs": 6000,
    "digitTimeoutMs": 3000,
    "status": 0,
    "result": 0,
    "pressedDigit": null,
    "initiatedAt": null,
    "ringingAt": null,
    "answeredAt": null,
    "completedAt": null,
    "callId": null,
    "errorMessage": null,
    "hangupCause": null,
    "creationTime": "2025-11-13T04:16:49.646512+03:00"
}
```

> 400 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Fires a webhook request to `webhookUrl` after the call terminates.

Here is the we webhook payload:
```
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "externalId": "optional-external-id",
  "workspaceId": "11111111-2222-3333-4444-555555555555",
  "channelId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "destinationNumber": "+966500000000",
  "status": "Pending | Initiated | Ringing | InProgress | Completed | NoAnswer | Busy | Failed",
  "result": "None | DigitPressed | NoInput | InvalidInput | NotAnswered | DestinationBusy | TechnicalFailure | Cancelled",
  "pressedDigit": "1",
  "initiatedAt": "2025-01-01T12:00:00Z",
  "ringingAt": "2025-01-01T12:00:02Z",
  "answeredAt": "2025-01-01T12:00:05Z",
  "completedAt": "2025-01-01T12:00:20Z",
  "callDurationSeconds": 15,
  "callId": "abcdabcd-abcd-abcd-abcd-abcdabcdabcd",
  "errorMessage": null,
  "hangupCause": "NORMAL_CLEARING",

  "creationTime": "2025-01-01T12:00:00Z"
}```|Inline|
|400|[Bad Request](https://tools.ietf.org/html/rfc7231#section-6.5.1)|none|Inline|
|500|[Internal Server Error](https://tools.ietf.org/html/rfc7231#section-6.6.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

*OutboundIvrWebhookPayload*

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» id|string(uuid)|true|none||none|
|» externalId|string¦null|false|none||none|
|» workspaceId|string(uuid)|true|none||none|
|» channelId|string(uuid)|true|none||none|
|» destinationNumber|string|true|none||none|
|» status|string|true|none||none|
|» result|string|true|none||none|
|» pressedDigit|string¦null|false|none||none|
|» initiatedAt|string(date-time)¦null|false|none||none|
|» ringingAt|string(date-time)¦null|false|none||none|
|» answeredAt|string(date-time)¦null|false|none||none|
|» completedAt|string(date-time)¦null|false|none||none|
|» callDurationSeconds|integer¦null|false|none||none|
|» callId|string(uuid)¦null|false|none||none|
|» errorMessage|string¦null|false|none||none|
|» hangupCause|string¦null|false|none||none|
|» creationTime|string(date-time)|true|none||none|

#### Enum

|Name|Value|
|---|---|
|status|Pending|
|status|InProgress|
|status|Completed|
|status|Failed|
|result|Success|
|result|NoAnswer|
|result|Busy|
|result|Failed|
|result|DtmfTimeout|

HTTP Status Code **500**

*OutboundIvrWebhookPayload*

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|

# Workspace API

## GET Get Workspace Users

GET /v1/workspaces/users

> Response Examples

> 200 Response

```json
[
  {
    "id": "497f6eca-6276-4993-bfeb-53cbbbba6f08",
    "workspaceId": "ef0efa32-d1c1-43d4-a5e2-fe7b4f00403c",
    "userId": "2c4a230c-5085-4924-a3e1-25fb4fc5965b",
    "email": "string",
    "name": "string",
    "logoUrl": "string",
    "role": 1,
    "creationTime": "2019-08-24T14:15:22Z",
    "isAiAgent": true,
    "phoneNumber": "string"
  }
]
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|none|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» id|string(uuid)|true|none||Workspace user record ID (or AI agent ID).|
|» workspaceId|string(uuid)|true|none||none|
|» userId|string(uuid)|true|none||The identity user ID (or AI agent ID if isAiAgent is true).|
|» email|string|false|none||User's email address. Null for AI agents.|
|» name|string|false|none||Display name of the user or AI agent.|
|» logoUrl|string|false|none||URL to the user's profile photo or AI agent avatar.|
|» role|integer|true|none||Workspace role. 1 = Owner, 2 = Member|
|» creationTime|string(date-time)|true|none||none|
|» isAiAgent|boolean|true|none||Whether this entry represents an AI agent rather than a human user.|
|» phoneNumber|string|false|none||User's phone number. Null for AI agents.|

#### Enum

|Name|Value|
|---|---|
|role|1|
|role|2|

# Conversations API

## GET Get Conversation Timeline

GET /v2/conversations/service-account/{conversationId}/timeline

Returns a paged list of timeline events for a conversation.

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|conversationId|path|string(uuid)| yes ||Conversation ID|
|Sorting|query|string| no ||Sorting expression (e.g. "CreationTime DESC")|
|SkipCount|query|integer| no ||Number of items to skip|
|MaxResultCount|query|integer| no ||Maximum number of items to return|

> Response Examples

> 200 Response

```json
{
    "TotalCount": 1,
    "Items": [
        {
            "EventId": "a1b2c3d4-5678-9abc-def0-123456789abc",
            "ConversationId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "ContactId": "8a2e0b4c-1234-5678-9abc-def012345678",
            "ChannelId": "b1c2d3e4-5678-9abc-def0-123456789abc",
            "SourceType": 1,
            "SourceId": "c2d3e4f5-6789-abcd-ef01-23456789abcd",
            "Direction": 1,
            "CreationTime": "2026-03-17T12:00:00Z",
            "Status": "Answered",
            "ErrorCode": null,
            "FailureReason": null,
            "IsAi": false,
            "Attachment": null,
            "OwnerUserId": null,
            "AiAgentId": null,
            "DurationOrSize": "00:02:30",
            "RingingDuration": "00:00:15",
            "Body": null,
            "HandlerName": "Agent Smith",
            "AiSummary": null,
            "ReplyTo": null,
            "InternalThread": null,
            "Location": null,
            "Assignation": null
        }
    ]
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Paged list of conversation timeline events|[PagedResultOfConversationTimelineDto](#schemapagedresultofconversationtimelinedto)|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized - missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden - token lacks VoxaAPIScope|None|

## GET List Conversations

GET /v2/conversations/service-account/channels/{channelId}

Returns a paged list of conversations for a channel.

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|channelId|path|string(uuid)| yes ||Channel ID to list conversations for|
|Status|query|integer| no ||Filter by conversation status. Omit for all statuses.|
|AssigneeUserIds|query|string| no ||Comma-separated list of user IDs to filter by assignee|
|GetUnAssigned|query|boolean| no ||If true, returns only unassigned conversations|
|ContactIds|query|string| no ||Comma-separated list of contact IDs to filter by|
|TagIds|query|string| no ||Comma-separated list of tag IDs to filter by|
|Name|query|string| no ||Filter by contact name|
|PhoneNumber|query|string| no ||Filter by contact phone number|
|FromDate|query|string(date-time)| no ||Start of date range filter (expected in UTC+3, converted to UTC internally)|
|ToDate|query|string(date-time)| no ||End of date range filter (expected in UTC+3, converted to UTC internally)|
|IsLost|query|boolean| no ||Filter for lost conversations (last event was inbound but not successfully addressed)|
|Sorting|query|string| no ||Sorting expression (e.g. "LastActivityAt DESC")|
|SkipCount|query|integer| no ||Number of items to skip|
|MaxResultCount|query|integer| no ||Maximum number of items to return|

#### Enum

|Name|Value|
|---|---|
|Status|1|
|Status|2|

> Response Examples

> 200 Response

```json
{
    "TotalCount": 1,
    "Items": [
        {
            "Id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "Sentiment": null,
            "Status": 1,
            "LastActivityAt": "2026-03-17T12:00:00Z",
            "ContactId": "8a2e0b4c-1234-5678-9abc-def012345678",
            "ContactName": "John Doe",
            "ContactType": 1,
            "PhoneNumber": "+966500111222",
            "ChannelId": "b1c2d3e4-5678-9abc-def0-123456789abc",
            "AssigneeId": null,
            "AssignedAiAgentId": null,
            "IsAiAssignee": false,
            "AssigneeName": null,
            "Channel": {
                "Id": "b1c2d3e4-5678-9abc-def0-123456789abc",
                "Name": "Main Line",
                "Type": 1,
                "Icon": null,
                "PhoneNumber": "+966500000001"
            },
            "LastEventSourceType": 1,
            "LastEventDirection": 1,
            "LastEventStatus": "Answered",
            "LastEventPreviewBody": null,
            "LastEventOccurredAt": "2026-03-17T12:00:00Z",
            "LastEventsCount": 3,
            "Tags": [],
            "UnreadCount": 0
        }
    ]
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Paged list of conversations|[PagedResultOfConversationDto](#schemapagedresultofconversationdto)|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized - missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden - token lacks VoxaAPIScope|None|

## POST Create Conversation

POST /v2/conversations/service-account/create

Creates a conversation for a contact. Returns existing conversation if it exists. Optionally assigns to a user or AI agent.

> Body Parameters

```json
{
    "ChannelId": "3a197b6e-e0b9-ce63-4664-a4d3eddae5a0",
    "PhoneNumber": "+966500888777",
    "ContactName": "Ahmed Ali",
    "AssignToUserId": null,
    "AssignToAiAgentId": null
}
```

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|body|body|object| no ||none|
|» ChannelId|body|string| yes ||The channel ID to create the conversation on|
|» PhoneNumber|body|string| yes ||Contact phone number (E.164 format)|
|» ContactName|body|string¦null| no ||Optional contact name. If omitted, phone number is used as the name|
|» AssignToUserId|body|string¦null| no ||Optional user ID to assign the conversation to|
|» AssignToAiAgentId|body|string¦null| no ||Optional AI agent ID to assign the conversation to|

> Response Examples

> 200 Response

```json
{
    "conversation": {
        "id": "3a1a4cb7-e7c1-f045-127b-ad2297847528",
        "status": "Open",
        "lastActivityAt": "2026-02-19T01:52:46Z",
        "contactId": "3a18a7e6-48bf-e5b8-4935-867e4b6c6c02",
        "contactName": "Ahmed Ali",
        "phoneNumber": "+966500888777",
        "channelId": "3a197b6e-e0b9-ce63-4664-a4d3eddae5a0",
        "assigneeId": null,
        "assignedAiAgentId": null,
        "isAiAssignee": false,
        "assigneeName": null,
        "tags": [],
        "unreadCount": 0
    },
    "contactId": "3a18a7e6-48bf-e5b8-4935-867e4b6c6c02"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Conversation created or retrieved successfully|Inline|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» conversation|object|false|none||none|
|»» id|string|false|none||none|
|»» sentiment|string¦null|false|none||none|
|»» status|string|false|none||none|
|»» lastActivityAt|string(date-time)|false|none||none|
|»» contactId|string|false|none||none|
|»» contactName|string¦null|false|none||none|
|»» contactType|string|false|none||none|
|»» phoneNumber|string¦null|false|none||none|
|»» channelId|string¦null|false|none||none|
|»» assigneeId|string¦null|false|none||none|
|»» assignedAiAgentId|string¦null|false|none||none|
|»» isAiAssignee|boolean|false|none||none|
|»» assigneeName|string¦null|false|none||none|
|»» channel|object¦null|false|none||none|
|»»» id|string|false|none||none|
|»»» name|string¦null|false|none||none|
|»»» type|string|false|none||none|
|»»» icon|string¦null|false|none||none|
|»»» phoneNumber|string¦null|false|none||none|
|»» tags|[string]|false|none||none|
|»» unreadCount|integer|false|none||none|
|» contactId|string|false|none||none|

## POST Assign Conversation

POST /v2/conversations/service-account/{conversationId}/assign

Assigns a conversation to a user or AI agent. Pass both as null to unassign. Cannot assign to both simultaneously.

> Body Parameters

```json
{
    "AssignedUserId": null,
    "AssignedAiAgentId": "00aec1fb-ffee-40cc-bf0e-33832c29c61a"
}
```

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|conversationId|path|string(uuid)| yes ||The conversation ID to assign|
|body|body|object| no ||none|
|» AssignedUserId|body|string¦null| no ||User ID to assign to, or null|
|» AssignedAiAgentId|body|string¦null| no ||AI agent ID to assign to, or null|

> Response Examples

> 200 Response

```json
{}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Conversation assigned successfully|Inline|

### Responses Data Schema

## GET Get Conversation

GET /v2/conversations/service-account/{conversationId}

Retrieves a conversation by ID.

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|conversationId|path|string| yes ||none|

> Response Examples

> 200 Response

```json
{
    "id": "3a1a4cb7-e7c1-f045-127b-ad2297847528",
    "status": "Open",
    "lastActivityAt": "2026-02-19T01:52:46Z",
    "contactId": "3a18a7e6-48bf-e5b8-4935-867e4b6c6c02",
    "contactName": "Ahmed Ali",
    "contactType": "Individual",
    "phoneNumber": "+966500888777",
    "channelId": "3a197b6e-e0b9-ce63-4664-a4d3eddae5a0",
    "assigneeId": null,
    "assignedAiAgentId": null,
    "isAiAssignee": false,
    "assigneeName": null,
    "channel": {
        "id": "3a197b6e-e0b9-ce63-4664-a4d3eddae5a0",
        "name": "Main Channel",
        "type": "Voice",
        "icon": null,
        "phoneNumber": "+966500000000"
    },
    "tags": [],
    "unreadCount": 0
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Conversation retrieved successfully|Inline|
|404|[Not Found](https://tools.ietf.org/html/rfc7231#section-6.5.4)|Conversation not found|None|

### Responses Data Schema

HTTP Status Code **200**

|Name|Type|Required|Restrictions|Title|description|
|---|---|---|---|---|---|
|» id|string|false|none||none|
|» sentiment|string¦null|false|none||none|
|» status|string|false|none||none|
|» lastActivityAt|string(date-time)|false|none||none|
|» contactId|string|false|none||none|
|» contactName|string¦null|false|none||none|
|» contactType|string|false|none||none|
|» phoneNumber|string¦null|false|none||none|
|» channelId|string¦null|false|none||none|
|» assigneeId|string¦null|false|none||none|
|» assignedAiAgentId|string¦null|false|none||none|
|» isAiAssignee|boolean|false|none||none|
|» assigneeName|string¦null|false|none||none|
|» channel|object¦null|false|none||none|
|»» id|string|false|none||none|
|»» name|string¦null|false|none||none|
|»» type|string|false|none||none|
|»» icon|string¦null|false|none||none|
|»» phoneNumber|string¦null|false|none||none|
|» tags|[string]|false|none||none|
|» unreadCount|integer|false|none||none|

# Tags API

## POST Create Tag

POST /v1/tags/service-account

Creates a new tag in the workspacs.

> Body Parameters

```json
{
    "Name": "VIP",
    "Icon": "star",
    "Description": "VIP customers",
    "IsPinned": true
}
```

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|body|body|object| yes ||none|
|» Name|body|string| yes ||Tag name|
|» Icon|body|string¦null| no ||Tag icon identifier|
|» Description|body|string¦null| no ||Tag description|
|» IsPinned|body|boolean| no ||Whether the tag is pinned on the sidebar.|

> Response Examples

> 200 Response

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "Name": "string",
  "Icon": "string",
  "IsPinned": true,
  "CreationTime": "2019-08-24T14:15:22Z"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Tag created successfully|[TagDto](#schematagdto)|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized – missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden – token lacks VoxaAPIScope|None|

## GET List Tags

GET /v1/tags/service-account

Returns a paged list of tags in the workspace.

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|Sorting|query|string| no ||Sorting expression (e.g. "Name ASC")|
|SkipCount|query|integer| no ||Number of items to skip|
|MaxResultCount|query|integer| no ||Maximum number of items to return|

> Response Examples

> 200 Response

```json
{
  "TotalCount": 0,
  "Items": [
    {
      "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
      "Name": "string",
      "Icon": "string",
      "IsPinned": true,
      "CreationTime": "2019-08-24T14:15:22Z"
    }
  ]
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Paged list of tags|[PagedResultOfTagDto](#schemapagedresultoftagdto)|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized – missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden – token lacks VoxaAPIScope|None|

## DELETE Delete Tag

DELETE /v1/tags/service-account/{id}

Deletes a tag by ID.

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|id|path|string(uuid)| yes ||Tag ID|

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|204|[No Content](https://tools.ietf.org/html/rfc7231#section-6.3.5)|Tag deleted successfully|None|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized – missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden – token lacks VoxaAPIScope|None|
|404|[Not Found](https://tools.ietf.org/html/rfc7231#section-6.5.4)|Tag not found|None|

## PUT Update Tag

PUT /v1/tags/service-account/{id}

Updates an existing tag. All fields are optional – only provided fields are updated.

> Body Parameters

```json
{
    "Name": "VIP Updated",
    "Icon": "crown",
    "Description": "Updated VIP tag",
    "IsPinned": false
}
```

### Params

|Name|Location|Type|Required|Title|Description|
|---|---|---|---|---|---|
|id|path|string(uuid)| yes ||Tag ID|
|body|body|[UpdateTagDto](#schemaupdatetagdto)| yes ||none|

> Response Examples

> 200 Response

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "Name": "string",
  "Icon": "string",
  "IsPinned": true,
  "CreationTime": "2019-08-24T14:15:22Z"
}
```

### Responses

|HTTP Status Code |Meaning|Description|Data schema|
|---|---|---|---|
|200|[OK](https://tools.ietf.org/html/rfc7231#section-6.3.1)|Tag updated successfully|[TagDto](#schematagdto)|
|401|[Unauthorized](https://tools.ietf.org/html/rfc7235#section-3.1)|Unauthorized – missing or invalid token|None|
|403|[Forbidden](https://tools.ietf.org/html/rfc7231#section-6.5.3)|Forbidden – token lacks VoxaAPIScope|None|
|404|[Not Found](https://tools.ietf.org/html/rfc7231#section-6.5.4)|Tag not found|None|

# Data Schema

<h2 id="tocS_Call Webhook">Call Webhook</h2>

<a id="schemacall webhook"></a>
<a id="schema_Call Webhook"></a>
<a id="tocScall webhook"></a>
<a id="tocscall webhook"></a>

```json
{
  "workspaceId": "ef0efa32-d1c1-43d4-a5e2-fe7b4f00403c",
  "channelId": "5f6d08bc-455a-4532-98b8-19e2cee51160",
  "status": 0,
  "type": 1,
  "callerNumber": "string",
  "calleeNumber": "string",
  "pickupTime": "2019-08-24T14:15:22Z",
  "hangupTime": "2019-08-24T14:15:22Z",
  "userId": "2c4a230c-5085-4924-a3e1-25fb4fc5965b",
  "userName": "string",
  "contactId": "b5ec5d98-4bee-4da1-ad24-dde86346cb1d",
  "contactNumber": "string",
  "callLength": "00:05:32",
  "aiAgentId": "de6aefb3-8e9c-49f1-b481-86af32c29492",
  "recordingUrl": "string",
  "transcription": {
    "text": "string",
    "words": [
      {
        "text": "string",
        "start": 0,
        "end": 0,
        "type": "string",
        "speaker": "string"
      }
    ]
  },
  "summary": "string",
  "sentiment": 1,
  "evaluationCriteriaResult": [
    {
      "id": "string",
      "dataType": "string",
      "description": "string",
      "value": "string",
      "rationale": "string"
    }
  ],
  "creationTime": "2019-08-24T14:15:22Z"
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|workspaceId|string(uuid)|true|none||The workspace this call belongs to.|
|channelId|string(uuid)|true|none||The channel this call was made on.|
|status|integer|true|none||Call status.<br /><br />- `0` = Active<br />- `1` = Completed<br />- `2` = Missed<br />- `3` = RejectedByCaller<br />- `4` = RejectedByCallee<br />- `5` = NoAnswer<br />- `6` = Cancelled<br />- `7` = Failed|
|type|integer|true|none||Call direction.<br /><br />- `1` = Inbound<br />- `2` = Outbound|
|callerNumber|string¦null|false|none||Phone number of the caller.|
|calleeNumber|string¦null|false|none||Phone number of the callee.|
|pickupTime|string(date-time)¦null|false|none||Timestamp when the call was answered.|
|hangupTime|string(date-time)¦null|false|none||Timestamp when the call ended.|
|userId|string(uuid)¦null|false|none||ID of the user who handled the call.|
|userName|string¦null|false|none||Display name of the user who handled the call.|
|contactId|string(uuid)¦null|false|none||ID of the contact associated with the call.|
|contactNumber|string¦null|false|none||Phone number of the contact.|
|callLength|string¦null|false|none||Duration of the call in HH:MM:SS format.|
|aiAgentId|string(uuid)¦null|false|none||ID of the AI agent that handled the call (null if not an AI call).|
|recordingUrl|string¦null|false|none||URL to the call recording audio file.|
|transcription|object¦null|false|none||Full transcription of the call.|
|» text|string¦null|false|none||Complete transcription text.|
|» words|[object]¦null|false|none||Word-level transcription with timing information.|
|»» text|string|true|none||The spoken word.|
|»» start|number|true|none||Start time in seconds.|
|»» end|number|true|none||End time in seconds.|
|»» type|string|true|none||Word type (e.g., 'word', 'punctuation').|
|»» speaker|string|true|none||Speaker identifier (e.g., 'agent', 'user').|
|summary|string¦null|false|none||AI-generated summary of the call.|
|sentiment|integer¦null|false|none||Overall sentiment of the call.<br /><br />- `1` = Positive<br />- `2` = Neutral<br />- `3` = Negative<br />- `4` = Mixed<br />- `5` = Unknown|
|evaluationCriteriaResult|[object]¦null|false|none||Results of AI evaluation criteria defined on the agent.|
|» id|string|false|none||Evaluation criterion ID.|
|» dataType|string|false|none||Data type of the result (e.g., 'String', 'Boolean').|
|» description|string|false|none||Description of the evaluation criterion.|
|» value|string|false|none||The evaluated value.|
|» rationale|string|false|none||AI reasoning for the evaluation result.|
|creationTime|string(date-time)|true|none||Timestamp when the call record was created.|

#### Enum

|Name|Value|
|---|---|
|status|0|
|status|1|
|status|2|
|status|3|
|status|4|
|status|5|
|status|6|
|status|7|
|type|1|
|type|2|
|sentiment|1|
|sentiment|2|
|sentiment|3|
|sentiment|4|
|sentiment|5|

<h2 id="tocS_WhatsApp Message Webhook">WhatsApp Message Webhook</h2>

<a id="schemawhatsapp message webhook"></a>
<a id="schema_WhatsApp Message Webhook"></a>
<a id="tocSwhatsapp message webhook"></a>
<a id="tocswhatsapp message webhook"></a>

```json
{
  "workspaceId": "ef0efa32-d1c1-43d4-a5e2-fe7b4f00403c",
  "channelId": "5f6d08bc-455a-4532-98b8-19e2cee51160",
  "conversationId": "ee6e55e8-45fe-4a3e-9bc8-4669f9fdf77a",
  "contactId": "b5ec5d98-4bee-4da1-ad24-dde86346cb1d",
  "messageId": "string",
  "direction": "Inbound",
  "messageType": "Text",
  "body": "string",
  "mediaUrl": "string",
  "mimeType": "string",
  "status": "Sent",
  "senderUserId": "2b0414b9-b88f-4722-84b0-333eb47e9180",
  "latitude": 0,
  "longitude": 0,
  "creationTime": "2019-08-24T14:15:22Z",
  "isBillable": true,
  "errorCode": 0,
  "errorReason": "string"
}

```

Payload sent when a WhatsApp message is sent or received on a channel with a configured WhatsApp webhook URL.

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|workspaceId|string(uuid)|true|none||The workspace this message belongs to.|
|channelId|string(uuid)|true|none||The channel this message was sent/received on.|
|conversationId|string(uuid)|true|none||The conversation this message belongs to.|
|contactId|string(uuid)|true|none||The contact associated with this message.|
|messageId|string¦null|false|none||Meta WhatsApp message ID.|
|direction|string|true|none||Message direction.<br /><br />- `Inbound` = Message received from the contact<br />- `Outbound` = Message sent to the contact|
|messageType|string|true|none||The type of WhatsApp message.|
|body|string¦null|false|none||Text body of the message. Present for text, template, and interactive messages.|
|mediaUrl|string¦null|false|none||URL to the media file. Present for image, video, audio, document, and sticker messages.|
|mimeType|string¦null|false|none||MIME type of the media file (e.g., 'image/jpeg', 'video/mp4').|
|status|string|true|none||Delivery status of the message.|
|senderUserId|string(uuid)¦null|false|none||ID of the Hatif user who sent the message (for outbound messages).|
|latitude|number¦null|false|none||Latitude for location messages.|
|longitude|number¦null|false|none||Longitude for location messages.|
|creationTime|string(date-time)|true|none||Timestamp when the message was created.|
|isBillable|boolean|true|none||Whether this message incurred a billing charge.|
|errorCode|integer¦null|false|none||WhatsApp error code if the message failed.|
|errorReason|string¦null|false|none||Human-readable error reason if the message failed.|

#### Enum

|Name|Value|
|---|---|
|direction|Inbound|
|direction|Outbound|
|messageType|Text|
|messageType|Image|
|messageType|Video|
|messageType|Audio|
|messageType|Document|
|messageType|Location|
|messageType|Contact|
|messageType|Sticker|
|messageType|Template|
|messageType|Interactive|
|status|Sent|
|status|Delivered|
|status|Read|
|status|Pending|
|status|Failed|

<h2 id="tocS_CreateTagDto">CreateTagDto</h2>

<a id="schemacreatetagdto"></a>
<a id="schema_CreateTagDto"></a>
<a id="tocScreatetagdto"></a>
<a id="tocscreatetagdto"></a>

```json
{
  "Name": "string",
  "Icon": "string",
  "Description": "string",
  "IsPinned": true
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Name|string|true|none||Tag name|
|Icon|string¦null|false|none||Tag icon identifier|
|Description|string¦null|false|none||Tag description|
|IsPinned|boolean|false|none||Whether the tag is pinned|

<h2 id="tocS_UpdateTagDto">UpdateTagDto</h2>

<a id="schemaupdatetagdto"></a>
<a id="schema_UpdateTagDto"></a>
<a id="tocSupdatetagdto"></a>
<a id="tocsupdatetagdto"></a>

```json
{
  "Name": "string",
  "Icon": "string",
  "Description": "string",
  "IsPinned": true
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Name|string¦null|false|none||Tag name|
|Icon|string¦null|false|none||Tag icon identifier|
|Description|string¦null|false|none||Tag description|
|IsPinned|boolean¦null|false|none||Whether the tag is pinned|

<h2 id="tocS_TagDto">TagDto</h2>

<a id="schematagdto"></a>
<a id="schema_TagDto"></a>
<a id="tocStagdto"></a>
<a id="tocstagdto"></a>

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "Name": "string",
  "Icon": "string",
  "IsPinned": true,
  "CreationTime": "2019-08-24T14:15:22Z"
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Id|string(uuid)|false|none||Tag ID|
|Name|string|false|none||Tag name|
|Icon|string¦null|false|none||Tag icon identifier|
|IsPinned|boolean|false|none||Whether the tag is pinned|
|CreationTime|string(date-time)|false|none||When the tag was created|

<h2 id="tocS_PagedResultOfTagDto">PagedResultOfTagDto</h2>

<a id="schemapagedresultoftagdto"></a>
<a id="schema_PagedResultOfTagDto"></a>
<a id="tocSpagedresultoftagdto"></a>
<a id="tocspagedresultoftagdto"></a>

```json
{
  "TotalCount": 0,
  "Items": [
    {
      "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
      "Name": "string",
      "Icon": "string",
      "IsPinned": true,
      "CreationTime": "2019-08-24T14:15:22Z"
    }
  ]
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|TotalCount|integer|false|none||Total number of tags matching the query|
|Items|[[TagDto](#schematagdto)]|false|none||List of tags for the current page|

<h2 id="tocS_ConversationDto">ConversationDto</h2>

<a id="schemaconversationdto"></a>
<a id="schema_ConversationDto"></a>
<a id="tocSconversationdto"></a>
<a id="tocsconversationdto"></a>

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "Sentiment": 0,
  "Status": 1,
  "LastActivityAt": "2019-08-24T14:15:22Z",
  "ContactId": "5d5ccd8e-252d-4619-b43e-535952c342e4",
  "ContactName": "string",
  "ContactType": 0,
  "PhoneNumber": "string",
  "ChannelId": "04b0b2a5-93cb-474d-8ea9-3df0f84eb0ff",
  "AssigneeId": "255c80c0-3ac6-4a93-8cf8-91a6815ba1cc",
  "AssignedAiAgentId": "3461ec9f-4c67-4c86-9e76-c5b8ec4cbdd0",
  "IsAiAssignee": true,
  "AssigneeName": "string",
  "Channel": {
    "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
    "Name": "string",
    "Type": 1,
    "Icon": "string",
    "PhoneNumber": "string"
  },
  "LastEventSourceType": 1,
  "LastEventDirection": 1,
  "LastEventStatus": "string",
  "LastEventPreviewBody": "string",
  "LastEventOccurredAt": "2019-08-24T14:15:22Z",
  "LastEventsCount": 0,
  "Tags": [
    {
      "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
      "Name": "string",
      "Icon": "string",
      "IsPinned": true,
      "CreationTime": "2019-08-24T14:15:22Z"
    }
  ],
  "UnreadCount": 0
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Id|string(uuid)|false|none||Conversation ID|
|Sentiment|integer¦null|false|none||AI-derived sentiment score|
|Status|integer|false|none||1 = Open, 2 = Closed|
|LastActivityAt|string(date-time)|false|none||Timestamp of last activity|
|ContactId|string(uuid)|false|none||Contact ID|
|ContactName|string¦null|false|none||Contact display name|
|ContactType|integer|false|none||Contact type|
|PhoneNumber|string¦null|false|none||Contact phone number in E.164 format|
|ChannelId|string(uuid)¦null|false|none||Channel ID|
|AssigneeId|string(uuid)¦null|false|none||Assigned user ID|
|AssignedAiAgentId|string(uuid)¦null|false|none||Assigned AI agent ID|
|IsAiAssignee|boolean|false|none||Whether the assignee is an AI agent|
|AssigneeName|string¦null|false|none||Name of the assigned user or AI agent|
|Channel|[ChannelConversationDto](#schemachannelconversationdto)|false|none||none|
|LastEventSourceType|integer¦null|false|none||1 = Call, 2 = WhatsApp, 3 = Assignation|
|LastEventDirection|integer¦null|false|none||1 = Inbound, 2 = Outbound, 3 = Internal|
|LastEventStatus|string|false|none||Status of the last event (e.g. Answered, Missed, Sent)|
|LastEventPreviewBody|string¦null|false|none||Preview text of the last WhatsApp message|
|LastEventOccurredAt|string(date-time)¦null|false|none||When the last event occurred|
|LastEventsCount|integer|false|none||Number of events in the conversation|
|Tags|[[TagDto](#schematagdto)]|false|none||Tags assigned to this conversation|
|UnreadCount|integer|false|none||Number of unread events (always 0 for service accounts)|

#### Enum

|Name|Value|
|---|---|
|Status|1|
|Status|2|
|LastEventSourceType|1|
|LastEventSourceType|2|
|LastEventSourceType|3|
|LastEventDirection|1|
|LastEventDirection|2|
|LastEventDirection|3|

<h2 id="tocS_ChannelConversationDto">ChannelConversationDto</h2>

<a id="schemachannelconversationdto"></a>
<a id="schema_ChannelConversationDto"></a>
<a id="tocSchannelconversationdto"></a>
<a id="tocschannelconversationdto"></a>

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "Name": "string",
  "Type": 1,
  "Icon": "string",
  "PhoneNumber": "string"
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Id|string(uuid)|false|none||Channel ID|
|Name|string¦null|false|none||Channel name|
|Type|integer|false|none||1 = PhoneNumber, 2 = WhatsApp, 3 = PhoneNumberAndWhatsapp|
|Icon|string¦null|false|none||Channel icon identifier|
|PhoneNumber|string¦null|false|none||Channel phone number|

#### Enum

|Name|Value|
|---|---|
|Type|1|
|Type|2|
|Type|3|

<h2 id="tocS_ConversationTimelineDto">ConversationTimelineDto</h2>

<a id="schemaconversationtimelinedto"></a>
<a id="schema_ConversationTimelineDto"></a>
<a id="tocSconversationtimelinedto"></a>
<a id="tocsconversationtimelinedto"></a>

```json
{
  "EventId": "219a0dfb-2d03-431e-be28-19bdc45be724",
  "ConversationId": "c2b5572d-5fa1-4af6-9a33-1ef18b3dc9a8",
  "ContactId": "5d5ccd8e-252d-4619-b43e-535952c342e4",
  "ChannelId": "04b0b2a5-93cb-474d-8ea9-3df0f84eb0ff",
  "SourceType": 1,
  "SourceId": "dbac54cd-2ad0-4c34-b943-246b49709b6c",
  "Direction": 1,
  "CreationTime": "2019-08-24T14:15:22Z",
  "Status": "string",
  "ErrorCode": 0,
  "FailureReason": "string",
  "IsAi": true,
  "Attachment": "string",
  "OwnerUserId": "aed507e2-a2aa-44ff-9cf5-afd1305cd2ac",
  "AiAgentId": "a7a17aba-b6d3-4b20-b495-33d6045bf59d",
  "DurationOrSize": "string",
  "RingingDuration": "string",
  "Body": "string",
  "HandlerName": "string",
  "AiSummary": {
    "Summary": "string",
    "Transcription": "string"
  },
  "ReplyTo": {
    "RepliedToEventId": "83aee00d-b06e-424d-bda0-6ce537034ac4",
    "RepliedToBody": "string"
  },
  "InternalThread": {
    "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
    "IsResolved": true,
    "MessageCount": 0
  },
  "Location": {
    "Latitude": 0.1,
    "Longitude": 0.1,
    "Name": "string",
    "Address": "string"
  },
  "Assignation": {
    "AssignedUserId": "2377db57-3495-46d5-9334-4dd16a5f3a55",
    "AssignedUserName": "string",
    "AssignedAiAgentId": "3461ec9f-4c67-4c86-9e76-c5b8ec4cbdd0",
    "AssignedAiAgentName": "string",
    "AssignedByUserId": "5325095d-606d-4f10-9dda-1533300873ca",
    "AssignedByUserName": "string"
  }
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|EventId|string(uuid)|false|none||Conversation event ID|
|ConversationId|string(uuid)|false|none||Parent conversation ID|
|ContactId|string(uuid)|false|none||Contact ID|
|ChannelId|string(uuid)|false|none||Channel ID|
|SourceType|integer|false|none||1 = Call, 2 = WhatsApp, 3 = Assignation|
|SourceId|string(uuid)¦null|false|none||ID of the source entity (Call ID or WhatsApp message ID)|
|Direction|integer|false|none||1 = Inbound, 2 = Outbound, 3 = Internal|
|CreationTime|string(date-time)|false|none||When the event was created|
|Status|string|false|none||Event status (e.g. Answered, Missed, Failed, Sent, Delivered, Read)|
|ErrorCode|integer¦null|false|none||Error code if the event failed|
|FailureReason|string¦null|false|none||Failure reason if the event failed|
|IsAi|boolean|false|none||Whether this event was handled by an AI agent|
|Attachment|string¦null|false|none||Attachment URL (for WhatsApp media messages)|
|OwnerUserId|string(uuid)¦null|false|none||User who handled the event|
|AiAgentId|string(uuid)¦null|false|none||AI agent who handled the event|
|DurationOrSize|string¦null|false|none||Call duration or media size (TimeSpan format, e.g. "00:02:30")|
|RingingDuration|string¦null|false|none||Call ringing duration (TimeSpan format)|
|Body|string¦null|false|none||Message body (for WhatsApp text messages)|
|HandlerName|string¦null|false|none||Name of the user or AI agent who handled the event|
|AiSummary|[AiSummaryDto](#schemaaisummarydto)|false|none||AI-generated call summary|
|ReplyTo|[ReplyInfoDto](#schemareplyinfodto)|false|none||WhatsApp reply context|
|InternalThread|[InternalThreadDto](#schemainternalthreaddto)|false|none||Internal discussion thread attached to an event|
|Location|[LocationMessageDto](#schemalocationmessagedto)|false|none||WhatsApp location message|
|Assignation|[AssignationInfoDto](#schemaassignationinfodto)|false|none||Conversation assignation event details|

#### Enum

|Name|Value|
|---|---|
|SourceType|1|
|SourceType|2|
|SourceType|3|
|Direction|1|
|Direction|2|
|Direction|3|

<h2 id="tocS_AiSummaryDto">AiSummaryDto</h2>

<a id="schemaaisummarydto"></a>
<a id="schema_AiSummaryDto"></a>
<a id="tocSaisummarydto"></a>
<a id="tocsaisummarydto"></a>

```json
{
  "Summary": "string",
  "Transcription": "string"
}

```

AI-generated call summary

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Summary|string¦null|false|none||Summary text|
|Transcription|string¦null|false|none||Call transcription|

<h2 id="tocS_ReplyInfoDto">ReplyInfoDto</h2>

<a id="schemareplyinfodto"></a>
<a id="schema_ReplyInfoDto"></a>
<a id="tocSreplyinfodto"></a>
<a id="tocsreplyinfodto"></a>

```json
{
  "RepliedToEventId": "83aee00d-b06e-424d-bda0-6ce537034ac4",
  "RepliedToBody": "string"
}

```

WhatsApp reply context

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|RepliedToEventId|string(uuid)¦null|false|none||Event ID being replied to|
|RepliedToBody|string¦null|false|none||Preview of the message being replied to|

<h2 id="tocS_InternalThreadDto">InternalThreadDto</h2>

<a id="schemainternalthreaddto"></a>
<a id="schema_InternalThreadDto"></a>
<a id="tocSinternalthreaddto"></a>
<a id="tocsinternalthreaddto"></a>

```json
{
  "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
  "IsResolved": true,
  "MessageCount": 0
}

```

Internal discussion thread attached to an event

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Id|string(uuid)|false|none||Thread ID|
|IsResolved|boolean|false|none||Whether the thread is resolved|
|MessageCount|integer|false|none||Number of messages in the thread|

<h2 id="tocS_LocationMessageDto">LocationMessageDto</h2>

<a id="schemalocationmessagedto"></a>
<a id="schema_LocationMessageDto"></a>
<a id="tocSlocationmessagedto"></a>
<a id="tocslocationmessagedto"></a>

```json
{
  "Latitude": 0.1,
  "Longitude": 0.1,
  "Name": "string",
  "Address": "string"
}

```

WhatsApp location message

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|Latitude|number(double)|false|none||Latitude|
|Longitude|number(double)|false|none||Longitude|
|Name|string¦null|false|none||Location name|
|Address|string¦null|false|none||Location address|

<h2 id="tocS_AssignationInfoDto">AssignationInfoDto</h2>

<a id="schemaassignationinfodto"></a>
<a id="schema_AssignationInfoDto"></a>
<a id="tocSassignationinfodto"></a>
<a id="tocsassignationinfodto"></a>

```json
{
  "AssignedUserId": "2377db57-3495-46d5-9334-4dd16a5f3a55",
  "AssignedUserName": "string",
  "AssignedAiAgentId": "3461ec9f-4c67-4c86-9e76-c5b8ec4cbdd0",
  "AssignedAiAgentName": "string",
  "AssignedByUserId": "5325095d-606d-4f10-9dda-1533300873ca",
  "AssignedByUserName": "string"
}

```

Conversation assignation event details

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|AssignedUserId|string(uuid)¦null|false|none||User assigned to|
|AssignedUserName|string¦null|false|none||Name of the user assigned to|
|AssignedAiAgentId|string(uuid)¦null|false|none||AI agent assigned to|
|AssignedAiAgentName|string¦null|false|none||Name of the AI agent assigned to|
|AssignedByUserId|string(uuid)¦null|false|none||User who performed the assignment|
|AssignedByUserName|string¦null|false|none||Name of the user who performed the assignment|

<h2 id="tocS_PagedResultOfConversationDto">PagedResultOfConversationDto</h2>

<a id="schemapagedresultofconversationdto"></a>
<a id="schema_PagedResultOfConversationDto"></a>
<a id="tocSpagedresultofconversationdto"></a>
<a id="tocspagedresultofconversationdto"></a>

```json
{
  "TotalCount": 0,
  "Items": [
    {
      "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
      "Sentiment": 0,
      "Status": 1,
      "LastActivityAt": "2019-08-24T14:15:22Z",
      "ContactId": "5d5ccd8e-252d-4619-b43e-535952c342e4",
      "ContactName": "string",
      "ContactType": 0,
      "PhoneNumber": "string",
      "ChannelId": "04b0b2a5-93cb-474d-8ea9-3df0f84eb0ff",
      "AssigneeId": "255c80c0-3ac6-4a93-8cf8-91a6815ba1cc",
      "AssignedAiAgentId": "3461ec9f-4c67-4c86-9e76-c5b8ec4cbdd0",
      "IsAiAssignee": true,
      "AssigneeName": "string",
      "Channel": {
        "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
        "Name": "string",
        "Type": 1,
        "Icon": "string",
        "PhoneNumber": "string"
      },
      "LastEventSourceType": 1,
      "LastEventDirection": 1,
      "LastEventStatus": "string",
      "LastEventPreviewBody": "string",
      "LastEventOccurredAt": "2019-08-24T14:15:22Z",
      "LastEventsCount": 0,
      "Tags": [
        {
          "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
          "Name": "string",
          "Icon": "string",
          "IsPinned": true,
          "CreationTime": "2019-08-24T14:15:22Z"
        }
      ],
      "UnreadCount": 0
    }
  ]
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|TotalCount|integer|false|none||Total number of conversations matching the query|
|Items|[[ConversationDto](#schemaconversationdto)]|false|none||List of conversations for the current page|

<h2 id="tocS_PagedResultOfConversationTimelineDto">PagedResultOfConversationTimelineDto</h2>

<a id="schemapagedresultofconversationtimelinedto"></a>
<a id="schema_PagedResultOfConversationTimelineDto"></a>
<a id="tocSpagedresultofconversationtimelinedto"></a>
<a id="tocspagedresultofconversationtimelinedto"></a>

```json
{
  "TotalCount": 0,
  "Items": [
    {
      "EventId": "219a0dfb-2d03-431e-be28-19bdc45be724",
      "ConversationId": "c2b5572d-5fa1-4af6-9a33-1ef18b3dc9a8",
      "ContactId": "5d5ccd8e-252d-4619-b43e-535952c342e4",
      "ChannelId": "04b0b2a5-93cb-474d-8ea9-3df0f84eb0ff",
      "SourceType": 1,
      "SourceId": "dbac54cd-2ad0-4c34-b943-246b49709b6c",
      "Direction": 1,
      "CreationTime": "2019-08-24T14:15:22Z",
      "Status": "string",
      "ErrorCode": 0,
      "FailureReason": "string",
      "IsAi": true,
      "Attachment": "string",
      "OwnerUserId": "aed507e2-a2aa-44ff-9cf5-afd1305cd2ac",
      "AiAgentId": "a7a17aba-b6d3-4b20-b495-33d6045bf59d",
      "DurationOrSize": "string",
      "RingingDuration": "string",
      "Body": "string",
      "HandlerName": "string",
      "AiSummary": {
        "Summary": "string",
        "Transcription": "string"
      },
      "ReplyTo": {
        "RepliedToEventId": "83aee00d-b06e-424d-bda0-6ce537034ac4",
        "RepliedToBody": "string"
      },
      "InternalThread": {
        "Id": "38a5a5bb-dc30-49a2-b175-1de0d1488c43",
        "IsResolved": true,
        "MessageCount": 0
      },
      "Location": {
        "Latitude": 0.1,
        "Longitude": 0.1,
        "Name": "string",
        "Address": "string"
      },
      "Assignation": {
        "AssignedUserId": "2377db57-3495-46d5-9334-4dd16a5f3a55",
        "AssignedUserName": "string",
        "AssignedAiAgentId": "3461ec9f-4c67-4c86-9e76-c5b8ec4cbdd0",
        "AssignedAiAgentName": "string",
        "AssignedByUserId": "5325095d-606d-4f10-9dda-1533300873ca",
        "AssignedByUserName": "string"
      }
    }
  ]
}

```

### Attribute

|Name|Type|Required|Restrictions|Title|Description|
|---|---|---|---|---|---|
|TotalCount|integer|false|none||Total number of timeline events matching the query|
|Items|[[ConversationTimelineDto](#schemaconversationtimelinedto)]|false|none||List of timeline events for the current page|

