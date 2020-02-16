export COMMIT_SHA=`git rev-parse HEAD`

for INDEX in {1993..2020}; do
  sed -e "s|__VERSION__|$COMMIT_SHA|g" -e "s|__INDEX__|$INDEX|g" deployments/job_polygon_daily_template.yaml | tee deployments/tmp/job_$INDEX.yaml
done

for INDEX in {1993..2020}; do
  kubectl apply -f deployments/tmp/job_$INDEX.yaml
  rm deployments/tmp/job_$INDEX.yaml
done