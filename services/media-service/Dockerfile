FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
# Route Maven Central through the Aliyun mirror for reliable builds on CN networks.
COPY .mvn/settings-docker.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
RUN apt-get update \
	&& apt-get install -y --no-install-recommends ffmpeg curl \
	&& rm -rf /var/lib/apt/lists/*
RUN mkdir -p /app/storage /app/logs
COPY --from=build /workspace/target/video-platform-0.0.1-SNAPSHOT.jar /app/video-platform.jar
EXPOSE 8081
ENTRYPOINT ["java", "-jar", "/app/video-platform.jar"]
