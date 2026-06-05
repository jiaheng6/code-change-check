import java

from MethodCall call
where call.getFile().getRelativePath() != ""
select
  call.getFile().getRelativePath(),
  call.getLocation().getStartLine(),
  call.getMethod().getQualifiedName(),
  call.getNumArgument()
