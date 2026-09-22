# Архитектура «Земля Радар»

## Цель

Собрать воспроизводимую фактическую базу по земельным участкам и связанным объектам, на которой позднее можно валидировать экономические модели.

## Конвейер

```text
external source
    ↓
raw immutable snapshot
    ↓
source-specific validation
    ↓
normalized source layer
    ↓
entities
    ↓
relations
    ↓
ParcelRecord / evidence graph
    ↓
audit
```

### Raw layer

Сохраняет исходные байты и provenance. Raw-данные не перезаписываются.

### Normalized source layer

Приводит поля конкретного источника к стабильной схеме, сохраняя ссылку на raw snapshot.

### Entity layer

Примеры сущностей:
- Parcel
- RoadFeature
- Municipality
- PlanningZone
- Restriction
- AuctionLot

### Relations

Примеры:
- parcel belongs_to municipality
- parcel intersects planning_zone
- parcel near road_feature
- parcel intersects restriction

Пространственный факт и юридический факт считаются разными утверждениями. Например, OSM может подтвердить наличие картографированной дороги; юридический доступ к участку требует другого источника.

## Экономический слой

Пока отключён. Он возвращается только после появления подтверждённых данных и отдельной валидации метода на исторических наблюдениях.
