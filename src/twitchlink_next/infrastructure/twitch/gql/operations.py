"""Twitch GQL query text, ported verbatim from TwitchLink 3.5.5's
``TwitchGQLOperations.py`` (docs/migration-map.md). These are ordinary
GraphQL queries against Twitch's own schema — not persisted-query
hashes; those only start appearing for the playback operations, which
are FASE 4c's scope, not FASE 4b's.

Each ``Operation`` pairs the query text with the variable names it
expects, mirroring the original's ``TwitchGQLOperation.load()`` shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Operation:
    query: str
    variable_names: tuple[str, ...]

    def build_payload(self, variables: dict[str, object]) -> dict[str, object]:
        return {
            "query": self.query,
            "variables": {name: variables.get(name) for name in self.variable_names},
        }


GET_CHANNEL = Operation(
    query="""
        query($id: ID $login: String) {
          user(id: $id login: $login) {
            id
            login
            displayName
            description
            createdAt
            profileImageURL(width: 300)
            roles {
              isPartner
              isAffiliate
            }
            followers {
              totalCount
            }
            stream {
              id
              title
              game {
                name
              }
              previewImageURL
              createdAt
              viewersCount
            }
          }
        }
    """,
    variable_names=("id", "login"),
)

GET_CHANNEL_VIDEOS = Operation(
    query="""
        query(
          $login: String!
          $type: BroadcastType
          $sort: VideoSort!
          $limit: Int!
          $cursor: Cursor
        ) {
          user(login: $login) {
            videos(type: $type, sort: $sort, first: $limit, after: $cursor) {
              edges {
                cursor
                node {
                  id
                  title
                  game {
                    name
                  }
                  previewThumbnailURL
                  owner {
                    id
                    login
                    displayName
                    profileImageURL(width: 300)
                    createdAt
                  }
                  lengthSeconds
                  createdAt
                  publishedAt
                  viewCount
                }
              }
              pageInfo {
                hasNextPage
              }
            }
          }
        }
    """,
    variable_names=("login", "type", "sort", "limit", "cursor"),
)

GET_CHANNEL_CLIPS = Operation(
    query="""
        query($login: String!, $filter: ClipsFilter!, $limit: Int!, $cursor: Cursor) {
          user(login: $login) {
            clips(criteria: {filter: $filter}, first: $limit, after: $cursor) {
              edges {
                cursor
                node {
                  id
                  title
                  game {
                    name
                  }
                  thumbnailURL
                  slug
                  broadcaster {
                    id
                    login
                    displayName
                    profileImageURL(width: 300)
                    createdAt
                  }
                  curator {
                    id
                    login
                    displayName
                    profileImageURL(width: 300)
                    createdAt
                  }
                  durationSeconds
                  createdAt
                  viewCount
                }
              }
              pageInfo {
                hasNextPage
              }
            }
          }
        }
    """,
    variable_names=("login", "filter", "limit", "cursor"),
)

GET_VIDEO = Operation(
    query="""
        query($id: ID!) {
          video(id: $id) {
            id
            title
            game {
              name
            }
            previewThumbnailURL
            owner {
              id
              login
              displayName
              profileImageURL(width: 300)
              createdAt
            }
            lengthSeconds
            createdAt
            publishedAt
            viewCount
          }
        }
    """,
    variable_names=("id",),
)

GET_CLIP = Operation(
    query="""
        query($slug: ID!) {
          clip(slug: $slug) {
            id
            title
            game {
              name
            }
            thumbnailURL
            slug
            broadcaster {
              id
              login
              displayName
              profileImageURL(width: 300)
              createdAt
            }
            curator {
              id
              login
              displayName
              profileImageURL(width: 300)
              createdAt
            }
            durationSeconds
            createdAt
            viewCount
          }
        }
    """,
    variable_names=("slug",),
)

# Master Plan §38 (FASE 4a): "No implementar GraphQL completo todavía."
# Master Plan §39 (FASE 4b, this phase): users/channels/streams/VOD/clips/
# search only. The three playback-access-token operations 3.5.5 also
# defines (persisted-query style, needing Integrity+user auth) are FASE
# 4c's "Twitch Playback" — intentionally not ported here.

# Which operations require a Client-Integrity header — ported exactly
# from TwitchGQLAPI.py's `_send()`: metadata-only lookups (GetChannel,
# GetVideo, GetClip) don't need it; listing a channel's videos or clips
# does.
OPERATIONS_REQUIRING_INTEGRITY = (GET_CHANNEL_VIDEOS, GET_CHANNEL_CLIPS)
