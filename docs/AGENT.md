# Agent Handoff Notes

> **Historical crawler-module notes.** This is not the current project handoff. Read `AI_STARTUP_HARNESS.md` and `AI_HANDOFF.md` for repository-wide work; use this file only when changing the legacy crawl module.

## Crawl Task Summary

This project now has a backend API for storing and querying crawled video metadata from video websites such as Bilibili. The crawler itself should run outside the controller; the Spring Boot API only receives normalized crawl results and persists them.

## Added Backend Module

Package:

`src/main/java/com/example/videoplatform/crawl/`

Files added:

- `CrawledVideo.java`
- `CrawledVideoRepository.java`
- `CrawledVideoService.java`
- `CrawledVideoController.java`
- `CrawlDtos.java`

API endpoints:

- `POST /api/crawled-videos` - create or update crawled metadata for the current authenticated user.
- `GET /api/crawled-videos?page=0&size=20` - list current user's crawled videos.
- `GET /api/crawled-videos?site=bilibili&page=0&size=20` - list by source site.
- `GET /api/crawled-videos/{id}` - get one crawled video record by id.

The endpoints use existing JWT authentication and return the existing `ApiResponse<T>` wrapper.

## Stored Metadata Fields

`CrawledVideo` stores:

- `site`
- `sourceVideoId`
- `title`
- `authorName`
- `authorId`
- `description`
- `pageUrl`
- `coverUrl`
- `durationSeconds`
- `publishedAt`
- `viewCount`
- `likeCount`
- `coinCount`
- `favoriteCount`
- `shareCount`
- `commentCount`
- `tagsJson`
- `rawJson`
- `crawledAt`
- `createdAt`
- `updatedAt`

`owner` is set from the authenticated username, so records are user-scoped.

## Bilibili Crawl Validation

Public Bilibili metadata crawling was tested successfully using:

`https://api.bilibili.com/x/web-interface/view?bvid=BV1GJ411x7h7`

Sample video used:

- BVID: `BV1GJ411x7h7`
- Duration: `213` seconds
- Title: official Rick Astley MV on Bilibili
- Metadata only; video file was not downloaded.

Successful saved record from local test:

- Record id: `203b55c0-48dd-40a0-9e8e-cb50346f19c7`
- `sourceVideoId`: `BV1GJ411x7h7`
- `durationSeconds`: `213`
- `viewCount`: around `99681834` at test time

## Bilibili Field Mapping

Map Bilibili `data` fields to the API request like this:

- `data.bvid` -> `sourceVideoId`
- `data.title` -> `title`
- `data.owner.name` -> `authorName`
- `data.owner.mid` -> `authorId`
- `data.desc` -> `description`
- `https://www.bilibili.com/video/{data.bvid}` -> `pageUrl`
- `data.pic` -> `coverUrl`
- `data.duration` -> `durationSeconds`
- `data.pubdate` -> `publishedAt`
- `data.stat.view` -> `viewCount`
- `data.stat.like` -> `likeCount`
- `data.stat.coin` -> `coinCount`
- `data.stat.favorite` -> `favoriteCount`
- `data.stat.share` -> `shareCount`
- `data.stat.reply` -> `commentCount`
- full `data` JSON -> `rawJson`
- current time -> `crawledAt`

## Validation Commands Run

Project tests passed:

`mvn test`

Result:

`BUILD SUCCESS`, `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0`

Local service was started with:

`mvn spring-boot:run`

Test user used during local validation:

- username: `crawltest`
- password: `crawltest123`

## Known Issues

- `/actuator/health` returned `503` during local testing because Redis was not running at `localhost:6379`. Normal auth and crawl APIs still worked.
- PowerShell requests containing Chinese text must send UTF-8 bytes and use `application/json; charset=utf-8`, otherwise Spring may throw `JSON parse error: Invalid UTF-8 middle byte`.
- Console output may display Chinese titles as question marks due to terminal encoding; that does not necessarily mean the API failed.
- Running Maven tests or Spring Boot updates `target/` files. Do not accidentally commit unrelated `target/`, upload, log, or generated files.

## Compliance Notes

- Only public metadata was tested.
- Do not bypass login, captcha, anti-bot systems, paywalls, or access controls.
- Do not download video files unless explicit authorization exists.
- Use rate limiting and retry backoff for batch crawling.

## Recommended Next Steps

1. Add integration tests for `POST /api/crawled-videos`, list, filter by site, and get by id.
2. Add a separate Bilibili crawler script or service that accepts BVIDs and posts results to the backend API.
3. Add a crawl task table if batch crawling is needed, with status, retry count, and error message.
4. Add rate limiting and exponential backoff for Bilibili requests.
5. Add a frontend page for listing crawled videos.
6. Decide whether `CrawledVideo` should link to existing workflow/video tasks via `taskId` or `videoId`.
7. Consider disabling Redis health checks in local development if Redis is optional.
